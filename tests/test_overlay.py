"""
test_overlay.py — 测试 overlay 模块
"""

from collections import deque

import pytest

from overlay import Overlay, WINDOW_WIDTH, WINDOW_HEIGHT


class TestNiceCeil:
    def test_zero_or_negative_returns_one(self):
        assert Overlay._nice_ceil(0) == 1
        assert Overlay._nice_ceil(-5) == 1

    def test_small_values(self):
        assert Overlay._nice_ceil(3) >= 3
        assert Overlay._nice_ceil(8) >= 8

    def test_round_numbers(self):
        c = Overlay._nice_ceil
        assert c(50) >= 50
        assert c(100) >= 100
        assert c(1000) >= 1000

    def test_large_values(self):
        c = Overlay._nice_ceil
        assert c(500_000) >= 500_000
        assert c(10_000_000) >= 10_000_000

    def test_result_always_at_least_input(self):
        import random
        for _ in range(200):
            v = random.uniform(0.1, 1_000_000)
            assert Overlay._nice_ceil(v) >= v

    def test_near_boundary(self):
        assert Overlay._nice_ceil(9.9) >= 9.9
        assert Overlay._nice_ceil(99) >= 99


class TestOverlayCreation:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_default_size(self):
        w = Overlay()
        assert w.width() == WINDOW_WIDTH
        assert w.height() == WINDOW_HEIGHT

    def test_frameless_and_topmost(self):
        w = Overlay()
        from PyQt5.QtCore import Qt
        f = w.windowFlags()
        assert f & Qt.FramelessWindowHint
        assert f & Qt.WindowStaysOnTopHint

    def test_update_data_empty_history(self):
        w = Overlay()
        w.update_data(deque(), 0.0, 0.0)

    def test_update_data_with_history(self):
        w = Overlay()
        hist = deque([(100.0, 200.0), (150.0, 250.0)], maxlen=60)
        w.update_data(hist, 1000.0, 500.0, 10000, 20000, 50000, 60000)

    def test_menu_actions(self):
        w = Overlay()
        assert w.show_stats_action is not None
        assert w.set_api_key_action is not None
        assert w.autostart_action is not None
        assert w.quit_action is not None
        assert w.autostart_action.isCheckable()

    def test_autostart_checked_toggle(self):
        w = Overlay()
        w.set_autostart_checked(True)
        assert w.autostart_action.isChecked()
        w.set_autostart_checked(False)
        assert not w.autostart_action.isChecked()


class TestOverlayBalance:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_default_no_balance(self):
        """未调用 update_balance 时 _balance_text 为 None。"""
        w = Overlay()
        assert w._balance_text is None
        assert w._balance_error is False

    def test_update_balance_display(self):
        """设置余额后 _balance_text 正确更新。"""
        w = Overlay()
        w.update_balance("DS CNY 110.00", has_error=False)
        assert w._balance_text == "DS CNY 110.00"
        assert w._balance_error is False

    def test_update_balance_error(self):
        """错误状态的余额显示。"""
        w = Overlay()
        w.update_balance("API Key 无效", has_error=True)
        assert w._balance_error is True

    def test_update_balance_none_hides(self):
        """text=None 时隐藏余额显示。"""
        w = Overlay()
        w.update_balance("DS CNY 110.00")
        w.update_balance(None)
        assert w._balance_text is None

    def test_balance_draw_does_not_crash(self):
        """验证绘制余额文本不会崩溃。"""
        w = Overlay()
        w.update_balance("DS CNY 110.00", has_error=False)
        w.repaint()
