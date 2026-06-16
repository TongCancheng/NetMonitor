"""
net_engine.py — 数据采集引擎

- 自动检测默认上网网卡
- 每秒采样网卡计数器
- 计算上下行速率 (bps)
- 更新累计统计
"""

import time
import psutil
import socket
import struct
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Sample:
    """一次采样点。"""
    timestamp: float
    tx_bytes: int     # 累计发送字节
    rx_bytes: int     # 累计接收字节


@dataclass
class Rate:
    """上下行速率 (bytes/s)。"""
    tx: float = 0.0
    rx: float = 0.0

    @property
    def tx_bps(self) -> float:
        return self.tx * 8

    @property
    def rx_bps(self) -> float:
        return self.rx * 8


def get_default_nic() -> Optional[str]:
    """自动检测活跃上网网卡。优先选择有实际流量的接口。"""
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        counters = psutil.net_io_counters(pernic=True)

        candidates = []
        for name, snics in addrs.items():
            if name not in stats:
                continue
            st = stats[name]
            if not st.isup:
                continue
            if name.lower().startswith("loopback") or name.lower().startswith("lo"):
                continue
            for snic in snics:
                if snic.family == socket.AF_INET and snic.address != "127.0.0.1":
                    c = counters.get(name)
                    total = (c.bytes_sent + c.bytes_recv) if c else 0
                    candidates.append((name, st.speed or 0, total))

        if not candidates:
            return None

        # 优先有流量的网卡，其次按速度降序
        candidates.sort(key=lambda x: (x[2] > 0, x[1]), reverse=True)
        return candidates[0][0]

    except Exception:
        return None


class NetEngine:
    """网络流量采集引擎。

    用法:
        engine = NetEngine(store)
        engine.start()          # 开始采集
        rate = engine.rate      # 当前速率 (Rate)
        history = engine.history  # deque of (tx_bps, rx_bps)

    每秒调用 engine.tick() 或连接到 QTimer。
    """

    HISTORY_LENGTH = 60  # 保留最近 60 个采样点用于波形图

    def __init__(self, store=None):
        self._store = store              # StatsStore | None
        self._nic_name: Optional[str] = None
        self._prev_sample: Optional[Sample] = None
        self._current_rate = Rate()

        # 波形图历史数据: (tx_bytes_per_sec, rx_bytes_per_sec)
        self.history: deque = deque(maxlen=self.HISTORY_LENGTH)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @property
    def rate(self) -> Rate:
        return self._current_rate

    @property
    def nic_name(self) -> Optional[str]:
        return self._nic_name

    def init(self, preferred_nic: Optional[str] = None) -> bool:
        """初始化网卡选择。返回是否成功。

        如果 preferred_nic 有流量则优先使用；
        如果 preferred_nic 无流量（如未插线的以太网），回退到自动检测。
        """
        if preferred_nic:
            counters = psutil.net_io_counters(pernic=True)
            if preferred_nic in counters:
                c = counters[preferred_nic]
                if (c.bytes_sent + c.bytes_recv) > 0:
                    self._nic_name = preferred_nic
                    return True
                # 网卡存在但无流量，回退到自动检测
        self._nic_name = get_default_nic()
        return self._nic_name is not None

    def tick(self) -> bool:
        """执行一次采样（每秒调用一次）。返回是否成功。"""
        if not self._nic_name:
            return False

        try:
            counters = psutil.net_io_counters(pernic=True)
            if self._nic_name not in counters:
                # 网卡名变了，重新检测
                self._nic_name = get_default_nic()
                if not self._nic_name:
                    return False

            c = counters[self._nic_name]
            now = time.time()
            curr = Sample(timestamp=now, tx_bytes=c.bytes_sent, rx_bytes=c.bytes_recv)

            if self._prev_sample is not None:
                dt = curr.timestamp - self._prev_sample.timestamp
                if dt > 0:
                    tx_rate = (curr.tx_bytes - self._prev_sample.tx_bytes) / dt
                    rx_rate = (curr.rx_bytes - self._prev_sample.rx_bytes) / dt
                    # 防止计数器重置导致的负值
                    self._current_rate = Rate(
                        tx=max(0.0, tx_rate),
                        rx=max(0.0, rx_rate),
                    )
                else:
                    self._current_rate = Rate()

            self.history.append((self._current_rate.tx, self._current_rate.rx))

            # 累加到统计存储
            if self._prev_sample is not None and self._store is not None:
                dt = curr.timestamp - self._prev_sample.timestamp
                if dt > 0 and dt < 10:  # 防范长时间暂停后的异常累加
                    tx_delta = max(0, curr.tx_bytes - self._prev_sample.tx_bytes)
                    rx_delta = max(0, curr.rx_bytes - self._prev_sample.rx_bytes)
                    self._store.add(tx_delta, rx_delta)

            self._prev_sample = curr
            return True

        except (OSError, psutil.Error):
            return False

    def reset_history(self) -> None:
        self.history.clear()


# ------------------------------------------------------------------
# 格式化工具
# ------------------------------------------------------------------

def _format_value(
    value: float,
    tiers: list[tuple[float, str, int]],  # (threshold, suffix, decimals)
    default_suffix: str,
    default_decimals: int = 0,
) -> str:
    """通用数量级格式化：按阈值匹配最高级别。"""
    for threshold, suffix, decimals in tiers:
        if value >= threshold:
            return f"{value / threshold:.{decimals}f}{suffix}"
    return f"{value:.{default_decimals}f}{default_suffix}"


_SPEED_TIERS: list[tuple[float, str, int]] = [
    (1_000_000_000, " Gb/s", 1),
    (1_000_000, " Mb/s", 1),
    (1_000, " Kb/s", 1),
]

_BYTE_TIERS: list[tuple[float, str, int]] = [
    (1_000_000_000, " GB", 2),
    (1_000_000, " MB", 2),
    (1_000, " KB", 2),
]

_TRAY_TIERS: list[tuple[float, str, int]] = [
    (1_000_000_000, "G", 1),
    (1_000_000, "M", 1),
    (1_000, "K", 1),
]


def format_speed(bytes_per_sec: float) -> str:
    """将 bytes/s 格式化为人类可读字符串，如 "1.2 MB/s"。"""
    return _format_value(bytes_per_sec * 8, _SPEED_TIERS, " b/s", 0)


def format_bytes(n: int) -> str:
    """将字节数格式化为人类可读字符串，如 "1.2 GB"。"""
    return _format_value(float(n), _BYTE_TIERS, " B", 0)


def format_tray_speed(bytes_per_sec: float) -> str:
    """压缩格式，用于托盘图标: "1.2M" / "0.8K" / "9.9G"。"""
    return _format_value(bytes_per_sec * 8, _TRAY_TIERS, "", 0)
