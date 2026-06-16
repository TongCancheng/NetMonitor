"""
test_net_store.py — 测试 net_store 模块

覆盖: _load_json, _save_json, StatsStore, ConfigStore
"""

import json
from datetime import datetime, timedelta

import pytest

from net_store import StatsStore, ConfigStore, _load_json, _save_json


# ======================================================================
# _load_json / _save_json
# ======================================================================

class TestLoadSaveJson:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        assert _load_json(tmp_path / "nope.json") == {}

    def test_load_valid(self, tmp_path):
        p = tmp_path / "a.json"
        p.write_text('{"x": 1}', encoding="utf-8")
        assert _load_json(p) == {"x": 1}

    def test_load_invalid_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{broken", encoding="utf-8")
        assert _load_json(p) == {}

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "r.json"
        _save_json(p, {"k": "v", "n": 42})
        assert _load_json(p) == {"k": "v", "n": 42}

    def test_atomic_no_tmp_left(self, tmp_path):
        p = tmp_path / "atomic.json"
        _save_json(p, {"x": 1})
        assert not p.with_suffix(".tmp").exists()


# ======================================================================
# StatsStore
# ======================================================================

class TestStatsStore:
    def test_add_and_get_today(self, tmp_path):
        store = StatsStore(filepath=tmp_path / "stats.json")
        store.add(1000, 500)
        assert store.get_today() == {"tx": 1000, "rx": 500}

    def test_add_accumulates(self, tmp_path):
        store = StatsStore(filepath=tmp_path / "stats.json")
        store.add(100, 50)
        store.add(200, 100)
        assert store.get_today() == {"tx": 300, "rx": 150}

    def test_add_updates_month(self, tmp_path):
        store = StatsStore(filepath=tmp_path / "stats.json")
        store.add(1000, 500)
        assert store.get_month() == {"tx": 1000, "rx": 500}

    def test_get_today_returns_copy(self, tmp_path):
        store = StatsStore(filepath=tmp_path / "stats.json")
        store.add(100, 50)
        t = store.get_today()
        t["tx"] = 99999
        assert store.get_today()["tx"] == 100

    def test_get_month_returns_copy(self, tmp_path):
        store = StatsStore(filepath=tmp_path / "stats.json")
        store.add(100, 50)
        m = store.get_month()
        m["tx"] = 99999
        assert store.get_month()["tx"] == 100

    def test_save_persists(self, tmp_path):
        p = tmp_path / "stats.json"
        store = StatsStore(filepath=p)
        store.add(500, 250)
        store.save()
        data = json.loads(p.read_text(encoding="utf-8"))
        today = datetime.now().strftime("%Y-%m-%d")
        assert data[today]["tx"] == 500

    def test_cleanup_removes_old_days(self, tmp_path):
        p = tmp_path / "stats.json"
        old = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        p.write_text(json.dumps({old: {"tx": 1, "rx": 1}, today: {"tx": 2, "rx": 2}}),
                      encoding="utf-8")
        store = StatsStore(filepath=p)
        store.save()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert old not in data

    def test_cleanup_keeps_recent_days(self, tmp_path):
        p = tmp_path / "stats.json"
        recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        p.write_text(json.dumps({recent: {"tx": 1, "rx": 1}, today: {"tx": 2, "rx": 2}}),
                      encoding="utf-8")
        store = StatsStore(filepath=p)
        store.save()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert recent in data

    def test_cleanup_removes_old_months(self, tmp_path):
        p = tmp_path / "stats.json"
        curr = datetime.now().strftime("%Y-%m")
        p.write_text(json.dumps({"2025-01": {"tx": 1, "rx": 1}, curr: {"tx": 2, "rx": 2}}),
                      encoding="utf-8")
        store = StatsStore(filepath=p)
        store.save()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "2025-01" not in data

    def test_cleanup_removes_invalid_date_keys(self, tmp_path):
        p = tmp_path / "stats.json"
        today = datetime.now().strftime("%Y-%m-%d")
        p.write_text(json.dumps({"bad-key": {"tx": 1, "rx": 1}, today: {"tx": 2, "rx": 2}}),
                      encoding="utf-8")
        store = StatsStore(filepath=p)
        store.save()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "bad-key" not in data


# ======================================================================
# ConfigStore
# ======================================================================

class TestConfigStore:
    def test_defaults(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        assert cfg.window_x is None
        assert cfg.window_y is None
        assert cfg.autostart is False
        assert cfg.nic_name is None

    def test_get_window_pos_default(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        assert cfg.get_window_pos() == (None, None)

    def test_set_window_pos(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        cfg.set_window_pos(300, 400)
        assert cfg.window_x == 300
        assert cfg.window_y == 400
        assert cfg.get_window_pos() == (300, 400)

    def test_autostart_property(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        cfg.autostart = True
        assert cfg.autostart is True

    def test_nic_name_property(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        cfg.nic_name = "WLAN"
        assert cfg.nic_name == "WLAN"

    def test_deepseek_api_key_property(self, tmp_path):
        cfg = ConfigStore(filepath=tmp_path / "c.json")
        assert cfg.deepseek_api_key is None
        cfg.deepseek_api_key = "sk-test123"
        assert cfg.deepseek_api_key == "sk-test123"

    def test_save_and_reload(self, tmp_path):
        p = tmp_path / "c.json"
        cfg = ConfigStore(filepath=p)
        cfg.set_window_pos(100, 200)
        cfg.autostart = True
        cfg.nic_name = "以太网"
        cfg.save()

        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["window_x"] == 100
        assert data["autostart"] is True

    def test_loads_existing(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"window_x": 50, "window_y": 60,
                                  "autostart": True, "nic_name": "WLAN"}),
                      encoding="utf-8")
        cfg = ConfigStore(filepath=p)
        assert cfg.get_window_pos() == (50, 60)
        assert cfg.autostart is True

    def test_partial_fills_defaults(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"autostart": True}), encoding="utf-8")
        cfg = ConfigStore(filepath=p)
        assert cfg.autostart is True
        assert cfg.window_x is None
