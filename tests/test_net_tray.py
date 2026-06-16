"""
test_net_tray.py — 测试 net_tray 模块
"""

import pytest


class TestRenderTrayIcon:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_returns_valid_icon(self):
        from net_tray import render_tray_icon
        from PyQt5.QtGui import QIcon
        icon = render_tray_icon("1.2M", "0.8K")
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_different_sizes(self):
        from net_tray import render_tray_icon
        from PyQt5.QtGui import QIcon
        for sz in [16, 24, 32]:
            icon = render_tray_icon("99", "99", size=sz)
            assert isinstance(icon, QIcon)
            assert not icon.isNull()

    def test_zero_values(self):
        from net_tray import render_tray_icon
        assert not render_tray_icon("0", "0").isNull()

    def test_large_text(self):
        from net_tray import render_tray_icon
        assert not render_tray_icon("999G", "999G").isNull()


class TestTrayIcon:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_creation(self):
        from net_tray import TrayIcon
        t = TrayIcon()
        assert t.show_action is not None
        assert t.quit_action is not None
        assert t.autostart_action.isCheckable()

    def test_autostart_toggle(self):
        from net_tray import TrayIcon
        t = TrayIcon()
        t.set_autostart_checked(True)
        assert t.autostart_action.isChecked()
        t.set_autostart_checked(False)
        assert not t.autostart_action.isChecked()

    def test_update_speed_no_crash(self):
        from net_tray import TrayIcon
        t = TrayIcon()
        t.update_speed(125_000, 62_500)

    def test_context_menu_has_actions(self):
        from net_tray import TrayIcon
        t = TrayIcon()
        menu = t.contextMenu()
        assert len(menu.actions()) >= 4
