"""
net_store.py — 持久化存储

StatsStore: 今日/本月流量统计 (stats.json)
ConfigStore: 窗口位置、自启状态等配置 (config.json)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# PyInstaller 兼容：打包后 __file__ 指向临时目录，改用 exe 所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent


def _load_json(filepath: Path) -> dict:
    """读取 JSON 文件，不存在则返回空 dict。"""
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_json(filepath: Path, data: dict) -> None:
    """原子写入 JSON 文件（先写临时文件再替换）。"""
    tmp = filepath.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(filepath)


class StatsStore:
    """流量统计持久化。

    stats.json 结构:
    {
        "2026-06-11": {"tx": 123456, "rx": 654321},
        "2026-06": {"tx": 12345678, "rx": 87654321}
    }
    """

    def __init__(self, filepath: Path | None = None):
        self.filepath = filepath or (BASE_DIR / "stats.json")
        self._data: dict = _load_json(self.filepath)
        self._check_rollover()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def add(self, tx_bytes: int, rx_bytes: int) -> None:
        """累加本次采样字节到今日和本月统计。"""
        now = datetime.now()
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")

        self._ensure_key(day_key)
        self._ensure_key(month_key)

        self._data[day_key]["tx"] += tx_bytes
        self._data[day_key]["rx"] += rx_bytes
        self._data[month_key]["tx"] += tx_bytes
        self._data[month_key]["rx"] += rx_bytes

    def get_today(self) -> dict:
        """返回 {"tx": int, "rx": int} 今日累计字节。"""
        day_key = datetime.now().strftime("%Y-%m-%d")
        self._ensure_key(day_key)
        return dict(self._data[day_key])

    def get_month(self) -> dict:
        """返回 {"tx": int, "rx": int} 本月累计字节。"""
        month_key = datetime.now().strftime("%Y-%m")
        self._ensure_key(month_key)
        return dict(self._data[month_key])

    def save(self) -> None:
        """立即写入磁盘。"""
        self._cleanup_old()
        _save_json(self.filepath, self._data)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _ensure_key(self, key: str) -> None:
        if key not in self._data:
            self._data[key] = {"tx": 0, "rx": 0}

    def _check_rollover(self) -> None:
        """检测跨天/跨月，自动清理旧键。"""
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        """移除超过本月的月和超过今天的日记录（保留最近7天详细）。"""
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        current_day = now.strftime("%Y-%m-%d")

        # 清理月记录（保留本月）
        months = {k for k in self._data if len(k) == 7 and k != current_month}
        for k in months:
            del self._data[k]

        # 清理日记录（保留最近7天）
        days = {k for k in self._data if len(k) == 10}
        for k in days:
            try:
                d = datetime.strptime(k, "%Y-%m-%d")
                if (now - d).days > 7:
                    del self._data[k]
            except ValueError:
                del self._data[k]


class ConfigStore:
    """用户配置持久化。

    config.json 结构:
    {
        "window_x": 100,
        "window_y": 100,
        "autostart": false,
        "nic_name": null,
        "deepseek_api_key": null,
        "show_deepseek_balance": true,
        "show_input_counter": true
    }
    """

    DEFAULTS = {
        "window_x": None,
        "window_y": None,
        "autostart": False,
        "nic_name": None,
        "deepseek_api_key": None,
        "show_deepseek_balance": True,
        "show_input_counter": True,
        "saved_key_count": 0,
        "saved_click_count": 0,
    }

    def __init__(self, filepath: Path | None = None):
        self.filepath = filepath or (BASE_DIR / "config.json")
        self._data = {**self.DEFAULTS, **_load_json(self.filepath)}

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @property
    def window_x(self):
        return self._data["window_x"]

    @window_x.setter
    def window_x(self, val):
        self._data["window_x"] = val

    @property
    def window_y(self):
        return self._data["window_y"]

    @window_y.setter
    def window_y(self, val):
        self._data["window_y"] = val

    @property
    def autostart(self):
        return self._data["autostart"]

    @autostart.setter
    def autostart(self, val):
        self._data["autostart"] = val

    @property
    def nic_name(self):
        return self._data["nic_name"]

    @nic_name.setter
    def nic_name(self, val):
        self._data["nic_name"] = val

    @property
    def deepseek_api_key(self):
        return self._data["deepseek_api_key"]

    @deepseek_api_key.setter
    def deepseek_api_key(self, val):
        self._data["deepseek_api_key"] = val

    @property
    def show_deepseek_balance(self):
        return self._data["show_deepseek_balance"]

    @show_deepseek_balance.setter
    def show_deepseek_balance(self, val):
        self._data["show_deepseek_balance"] = val

    @property
    def show_input_counter(self):
        return self._data["show_input_counter"]

    @show_input_counter.setter
    def show_input_counter(self, val):
        self._data["show_input_counter"] = val

    @property
    def saved_key_count(self):
        return self._data["saved_key_count"]

    @saved_key_count.setter
    def saved_key_count(self, val):
        self._data["saved_key_count"] = val

    @property
    def saved_click_count(self):
        return self._data["saved_click_count"]

    @saved_click_count.setter
    def saved_click_count(self, val):
        self._data["saved_click_count"] = val

    def get_window_pos(self):
        """返回 (x, y) 或 (None, None)。"""
        return self._data["window_x"], self._data["window_y"]

    def set_window_pos(self, x: int, y: int) -> None:
        self._data["window_x"] = x
        self._data["window_y"] = y

    def save(self) -> None:
        """立即写入磁盘。"""
        _save_json(self.filepath, self._data)
