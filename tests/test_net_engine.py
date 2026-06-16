"""
test_net_engine.py — 测试 net_engine 模块

覆盖: format_speed, format_bytes, format_tray_speed, Rate, Sample,
      get_default_nic, NetEngine
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from net_engine import (
    Sample,
    Rate,
    format_speed,
    format_bytes,
    format_tray_speed,
    get_default_nic,
    NetEngine,
)


# ======================================================================
# Sample & Rate dataclass
# ======================================================================

class TestSample:
    def test_creation(self):
        s = Sample(timestamp=1234567890.0, tx_bytes=1000, rx_bytes=2000)
        assert s.timestamp == 1234567890.0
        assert s.tx_bytes == 1000
        assert s.rx_bytes == 2000

    def test_requires_all_fields(self):
        with pytest.raises(TypeError):
            Sample()  # type: ignore


class TestRate:
    def test_defaults(self):
        r = Rate()
        assert r.tx == 0.0
        assert r.rx == 0.0

    def test_bps_conversion(self):
        r = Rate(tx=1000.0, rx=500.0)
        assert r.tx_bps == 8000.0
        assert r.rx_bps == 4000.0

    def test_zero_bps(self):
        r = Rate()
        assert r.tx_bps == 0.0
        assert r.rx_bps == 0.0

    def test_fractional(self):
        r = Rate(tx=1.5, rx=2.5)
        assert r.tx_bps == 12.0
        assert r.rx_bps == 20.0


# ======================================================================
# 格式化函数
# ======================================================================

class TestFormatSpeed:
    def test_bits(self):
        assert format_speed(1) == "8 b/s"
        assert format_speed(100) == "800 b/s"

    def test_kilobits(self):
        assert format_speed(125) == "1.0 Kb/s"

    def test_megabits(self):
        assert format_speed(125_000) == "1.0 Mb/s"

    def test_gigabits(self):
        assert format_speed(125_000_000) == "1.0 Gb/s"

    def test_zero(self):
        assert format_speed(0) == "0 b/s"


class TestFormatBytes:
    def test_bytes(self):
        assert format_bytes(0) == "0 B"
        assert format_bytes(500) == "500 B"

    def test_kb(self):
        assert format_bytes(1_000) == "1.00 KB"

    def test_mb(self):
        assert format_bytes(1_000_000) == "1.00 MB"

    def test_gb(self):
        assert format_bytes(1_000_000_000) == "1.00 GB"

    def test_large(self):
        result = format_bytes(2_000_000_000_000)
        assert "GB" in result
        assert float(result.split()[0]) > 1000


class TestFormatTraySpeed:
    def test_small(self):
        assert format_tray_speed(1) == "8"

    def test_kilo(self):
        assert format_tray_speed(125) == "1.0K"

    def test_mega(self):
        assert format_tray_speed(125_000) == "1.0M"

    def test_giga(self):
        assert format_tray_speed(125_000_000) == "1.0G"

    def test_zero(self):
        assert format_tray_speed(0) == "0"

# ======================================================================
# get_default_nic
# ======================================================================

class TestGetDefaultNic:
    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_returns_fastest_when_both_no_traffic(self, mock_stats, mock_addrs, mock_counters):
        import socket
        mock_addrs.return_value = {
            "以太网": [MagicMock(family=socket.AF_INET, address="192.168.1.100")],
            "WLAN": [MagicMock(family=socket.AF_INET, address="10.0.0.5")],
        }
        mock_stats.return_value = {
            "以太网": MagicMock(isup=True, speed=1000),
            "WLAN": MagicMock(isup=True, speed=866),
        }
        mock_counters.return_value = {
            "以太网": MagicMock(bytes_sent=0, bytes_recv=0),
            "WLAN": MagicMock(bytes_sent=0, bytes_recv=0),
        }
        assert get_default_nic() == "以太网"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_prefers_nic_with_traffic(self, mock_stats, mock_addrs, mock_counters):
        """有流量的网卡优先，即使速度更低。"""
        import socket
        mock_addrs.return_value = {
            "以太网": [MagicMock(family=socket.AF_INET, address="192.168.1.100")],
            "WLAN": [MagicMock(family=socket.AF_INET, address="10.0.0.5")],
        }
        mock_stats.return_value = {
            "以太网": MagicMock(isup=True, speed=1000),
            "WLAN": MagicMock(isup=True, speed=866),
        }
        mock_counters.return_value = {
            "以太网": MagicMock(bytes_sent=0, bytes_recv=0),
            "WLAN": MagicMock(bytes_sent=5000, bytes_recv=10000),
        }
        assert get_default_nic() == "WLAN"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_excludes_loopback(self, mock_stats, mock_addrs, mock_counters):
        import socket
        mock_addrs.return_value = {
            "Loopback Pseudo-Interface 1": [
                MagicMock(family=socket.AF_INET, address="127.0.0.1")],
            "WLAN": [MagicMock(family=socket.AF_INET, address="192.168.1.1")],
        }
        mock_stats.return_value = {
            "Loopback Pseudo-Interface 1": MagicMock(isup=True, speed=1000),
            "WLAN": MagicMock(isup=True, speed=500),
        }
        mock_counters.return_value = {
            "Loopback Pseudo-Interface 1": MagicMock(bytes_sent=0, bytes_recv=0),
            "WLAN": MagicMock(bytes_sent=100, bytes_recv=200),
        }
        assert get_default_nic() == "WLAN"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_excludes_down(self, mock_stats, mock_addrs, mock_counters):
        import socket
        mock_addrs.return_value = {
            "以太网": [MagicMock(family=socket.AF_INET, address="192.168.1.100")],
            "WLAN": [MagicMock(family=socket.AF_INET, address="10.0.0.5")],
        }
        mock_stats.return_value = {
            "以太网": MagicMock(isup=False, speed=1000),
            "WLAN": MagicMock(isup=True, speed=866),
        }
        mock_counters.return_value = {
            "以太网": MagicMock(bytes_sent=0, bytes_recv=0),
            "WLAN": MagicMock(bytes_sent=100, bytes_recv=200),
        }
        assert get_default_nic() == "WLAN"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_no_candidates_returns_none(self, mock_stats, mock_addrs, mock_counters):
        mock_addrs.return_value = {}
        mock_stats.return_value = {}
        mock_counters.return_value = {}
        assert get_default_nic() is None

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_only_loopback_returns_none(self, mock_stats, mock_addrs, mock_counters):
        import socket
        mock_addrs.return_value = {
            "lo": [MagicMock(family=socket.AF_INET, address="127.0.0.1")],
        }
        mock_stats.return_value = {"lo": MagicMock(isup=True, speed=1000)}
        mock_counters.return_value = {"lo": MagicMock(bytes_sent=0, bytes_recv=0)}
        assert get_default_nic() is None

    @patch("net_engine.psutil.net_if_addrs")
    @patch("net_engine.psutil.net_if_stats")
    def test_exception_returns_none(self, mock_stats, mock_addrs):
        mock_addrs.side_effect = OSError("模拟异常")
        assert get_default_nic() is None

# ======================================================================
# NetEngine
# ======================================================================

class TestNetEngine:
    def test_init_defaults(self):
        engine = NetEngine()
        assert engine.nic_name is None
        assert engine.rate.tx == 0.0
        assert engine.rate.rx == 0.0
        assert len(engine.history) == 0
        assert engine.history.maxlen == 60

    @patch("net_engine.psutil.net_io_counters")
    def test_init_with_valid_preferred_nic(self, mock_io):
        """有流量的 preferred_nic 直接使用。"""
        mock_io.return_value = {
            "WLAN": MagicMock(bytes_sent=5000, bytes_recv=10000),
        }
        engine = NetEngine()
        assert engine.init(preferred_nic="WLAN") is True
        assert engine.nic_name == "WLAN"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.get_default_nic")
    def test_init_invalid_preferred_falls_back(self, mock_default, mock_io):
        mock_io.return_value = {"以太网": MagicMock(bytes_sent=100, bytes_recv=200)}
        mock_default.return_value = "以太网"
        engine = NetEngine()
        assert engine.init(preferred_nic="nonexistent") is True
        assert engine.nic_name == "以太网"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.get_default_nic")
    def test_init_preferred_no_traffic_falls_back(self, mock_default, mock_io):
        """preferred_nic 存在但无流量 → 回退到自动检测。"""
        mock_io.return_value = {
            "以太网": MagicMock(bytes_sent=0, bytes_recv=0),
            "WLAN": MagicMock(bytes_sent=5000, bytes_recv=10000),
        }
        mock_default.return_value = "WLAN"
        engine = NetEngine()
        assert engine.init(preferred_nic="以太网") is True
        assert engine.nic_name == "WLAN"

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.get_default_nic")
    def test_init_nothing_found(self, mock_default, mock_io):
        mock_io.return_value = {}
        mock_default.return_value = None
        engine = NetEngine()
        assert engine.init() is False

    def test_tick_false_without_nic(self):
        assert NetEngine().tick() is False

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_first_sample_no_rate(self, mock_io):
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=1000, bytes_recv=2000)}
        engine = NetEngine()
        engine.init(preferred_nic="WLAN")
        assert engine.tick() is True
        assert engine.rate.tx == 0.0
        assert engine.rate.rx == 0.0
        assert len(engine.history) == 1

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_calculates_rate(self, mock_io):
        engine = NetEngine()
        engine._nic_name = "WLAN"
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=1000, bytes_recv=2000)}
        engine.tick()
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=2000, bytes_recv=3000)}
        with patch("net_engine.time.time") as mock_time:
            mock_time.return_value = engine._prev_sample.timestamp + 1.0
            assert engine.tick() is True
        assert engine.rate.tx == pytest.approx(1000.0)
        assert engine.rate.rx == pytest.approx(1000.0)

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_counter_reset_clamped_to_zero(self, mock_io):
        engine = NetEngine()
        engine._nic_name = "WLAN"
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=50000, bytes_recv=100000)}
        engine.tick()
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=100, bytes_recv=200)}
        with patch("net_engine.time.time") as mock_time:
            mock_time.return_value = engine._prev_sample.timestamp + 1.0
            engine.tick()
        assert engine.rate.tx == 0.0
        assert engine.rate.rx == 0.0

    @patch("net_engine.psutil.net_io_counters")
    @patch("net_engine.get_default_nic")
    def test_tick_redetects_nic(self, mock_default, mock_io):
        engine = NetEngine()
        engine._nic_name = "old_nic"
        mock_io.return_value = {"other_nic": MagicMock(bytes_sent=0, bytes_recv=0)}
        mock_default.return_value = "other_nic"
        assert engine.tick() is True
        assert engine.nic_name == "other_nic"

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_accumulates_to_store(self, mock_io):
        mock_store = MagicMock()
        engine = NetEngine(store=mock_store)
        engine._nic_name = "WLAN"
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=1000, bytes_recv=2000)}
        engine.tick()
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=2000, bytes_recv=3000)}
        with patch("net_engine.time.time") as mock_time:
            mock_time.return_value = engine._prev_sample.timestamp + 1.0
            engine.tick()
        mock_store.add.assert_called_once_with(1000, 1000)

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_skips_store_on_long_pause(self, mock_io):
        mock_store = MagicMock()
        engine = NetEngine(store=mock_store)
        engine._nic_name = "WLAN"
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=1000, bytes_recv=2000)}
        engine.tick()
        mock_io.return_value = {"WLAN": MagicMock(bytes_sent=100000, bytes_recv=200000)}
        with patch("net_engine.time.time") as mock_time:
            mock_time.return_value = engine._prev_sample.timestamp + 30.0
            engine.tick()
        mock_store.add.assert_not_called()

    def test_reset_history(self):
        engine = NetEngine()
        engine.history.append((100.0, 200.0))
        engine.history.append((150.0, 250.0))
        engine.reset_history()
        assert len(engine.history) == 0

    @patch("net_engine.psutil.net_io_counters")
    def test_tick_oserror_returns_false(self, mock_io):
        mock_io.side_effect = OSError("模拟错误")
        engine = NetEngine()
        engine._nic_name = "WLAN"
        assert engine.tick() is False
