"""
input_counter.py — 全局键盘鼠标点击计数

使用 pynput 库监听全局键盘/鼠标事件，pynput 内部管理
Windows 消息泵和线程，不会与 Qt 主循环争夺 GIL 导致 UI 卡顿。
"""

import threading
from pynput import keyboard, mouse


class InputCounter:
    """全局键盘 / 鼠标点击计数器。

    用法:
        counter = InputCounter()
        counter.start()                 # 启动监听
        k, c = counter.key_count, counter.click_count
        counter.stop()                  # 停止监听
    """

    def __init__(self):
        self._key_count = 0
        self._click_count = 0
        self._lock = threading.Lock()
        self._kbd_listener: keyboard.Listener | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._running = False

    @property
    def key_count(self) -> int:
        with self._lock:
            return self._key_count

    @property
    def click_count(self) -> int:
        with self._lock:
            return self._click_count

    def start(self) -> None:
        """启动键盘和鼠标监听器。"""
        if self._running:
            return
        self._running = True
        try:
            self._kbd_listener = keyboard.Listener(on_press=self._on_press)
            self._mouse_listener = mouse.Listener(on_click=self._on_click)
            self._kbd_listener.start()
            self._mouse_listener.start()
        except Exception:
            self._running = False
            self._kbd_listener = None
            self._mouse_listener = None
            raise

    def stop(self) -> None:
        """停止监听器。"""
        self._running = False
        if self._kbd_listener:
            self._kbd_listener.stop()
            self._kbd_listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

    def load_counts(self, key_count: int = 0, click_count: int = 0) -> None:
        """恢复初始计数值（用于跨重启持久化）。"""
        with self._lock:
            self._key_count = key_count
            self._click_count = click_count

    def snapshot(self) -> tuple[int, int]:
        """返回 (key_count, click_count) 快照。"""
        with self._lock:
            return self._key_count, self._click_count

    def reset(self) -> None:
        """清零计数。"""
        with self._lock:
            self._key_count = 0
            self._click_count = 0

    # ------------------------------------------------------------------
    # pynput 回调
    # ------------------------------------------------------------------

    def _on_press(self, key):
        """键盘按下回调（由 pynput 内部线程调用）。"""
        with self._lock:
            self._key_count += 1

    def _on_click(self, x, y, button, pressed):
        """鼠标点击回调，只在按下时计数。"""
        if pressed:
            with self._lock:
                self._click_count += 1
