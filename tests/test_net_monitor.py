"""
test_net_monitor.py — 测试 net_monitor 模块
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from net_monitor import (
    _get_pythonw_path,
    autostart_is_enabled,
    autostart_enable,
    autostart_disable,
    autostart_sync,
    LNK_NAME,
)


class TestGetPythonwPath:
    def test_replaces_python_with_pythonw(self):
        with patch.object(sys, "executable", r"C:\Py\python.exe"):
            assert _get_pythonw_path() == r"C:\Py\pythonw.exe"

    def test_keeps_pythonw(self):
        with patch.object(sys, "executable", r"C:\Py\pythonw.exe"):
            assert _get_pythonw_path() == r"C:\Py\pythonw.exe"

    def test_other_exe_unchanged(self):
        with patch.object(sys, "executable", r"/usr/bin/python3"):
            assert _get_pythonw_path() == r"/usr/bin/python3"


class TestAutostart:
    def test_enable_creates_shortcut(self, tmp_path, monkeypatch):
        """启用自启：调用 _create_shortcut 创建 .lnk 文件。"""
        startup = tmp_path / "Startup"
        startup.mkdir()
        lnk_path = startup / LNK_NAME
        monkeypatch.setattr("net_monitor.STARTUP_DIR", startup)
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk_path)
        monkeypatch.setattr(sys, "executable", r"C:\Py\python.exe")
        monkeypatch.setattr("net_monitor.BASE_DIR", tmp_path)
        (tmp_path / "net_monitor.py").write_text("# stub")

        # Mock _create_shortcut 避免真正调用 PowerShell
        with patch("net_monitor._create_shortcut", return_value=True) as mock_cs:
            assert autostart_enable() is True
            mock_cs.assert_called_once()
            args = mock_cs.call_args[1]
            assert args["target"] == r"C:\Py\pythonw.exe"
            assert "net_monitor.py" in args["arguments"]

    def test_enable_catches_oserror(self, tmp_path, monkeypatch):
        """STARTUP_DIR 创建失败时返回 False。"""
        from pathlib import Path as PathCls
        monkeypatch.setattr("net_monitor.STARTUP_DIR",
                            tmp_path / "no_dir")
        with patch.object(PathCls, "mkdir", side_effect=OSError("err")):
            assert autostart_enable() is False

    def test_disable_removes_lnk(self, tmp_path, monkeypatch):
        """禁用自启：删除 .lnk 文件。"""
        startup = tmp_path / "Startup"
        startup.mkdir()
        lnk = startup / LNK_NAME
        lnk.write_text("stub")
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        assert autostart_disable() is True
        assert not lnk.exists()

    def test_disable_nonexistent_ok(self, tmp_path, monkeypatch):
        startup = tmp_path / "Startup"
        startup.mkdir()
        lnk = startup / LNK_NAME
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        assert autostart_disable() is True

    def test_is_enabled_true(self, tmp_path, monkeypatch):
        startup = tmp_path / "Startup"
        startup.mkdir()
        lnk = startup / LNK_NAME
        lnk.write_text("x")
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        assert autostart_is_enabled() is True

    def test_is_enabled_false(self, tmp_path, monkeypatch):
        lnk = tmp_path / LNK_NAME
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        assert autostart_is_enabled() is False

    def test_sync_enable(self, tmp_path, monkeypatch):
        startup = tmp_path / "Startup"
        startup.mkdir()
        monkeypatch.setattr("net_monitor.STARTUP_DIR", startup)
        monkeypatch.setattr("net_monitor._startup_lnk_path",
                            lambda: startup / LNK_NAME)
        monkeypatch.setattr(sys, "executable", r"C:\Py\python.exe")
        monkeypatch.setattr("net_monitor.BASE_DIR", tmp_path)
        (tmp_path / "net_monitor.py").write_text("# stub")
        with patch("net_monitor._create_shortcut", return_value=True):
            assert autostart_sync(True) is True

    def test_sync_disable(self, tmp_path, monkeypatch):
        startup = tmp_path / "Startup"
        startup.mkdir()
        lnk = startup / LNK_NAME
        lnk.write_text("x")
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        assert autostart_sync(False) is True
        assert not lnk.exists()

    def test_disable_oserror_returns_false(self, tmp_path, monkeypatch):
        lnk = tmp_path / LNK_NAME
        lnk.write_text("stub")
        monkeypatch.setattr("net_monitor._startup_lnk_path", lambda: lnk)
        with patch.object(type(lnk), "unlink", side_effect=OSError("err")):
            assert autostart_disable() is False

    def test_create_shortcut_calls_powershell(self, monkeypatch):
        """验证 _create_shortcut 调用 PowerShell 正确传参。"""
        import subprocess
        mock_run = patch.object(subprocess, "run", return_value=None).start()
        try:
            from net_monitor import _create_shortcut
            result = _create_shortcut(
                target=r"C:\Py\pythonw.exe",
                shortcut_path=r"C:\Startup\NetMonitor.lnk",
                arguments='"B:\\test.py"',
                working_dir="B:\\",
            )
            assert result is True
            assert mock_run.call_count == 1
            ps_cmd = mock_run.call_args[0][0]
            assert "powershell" in ps_cmd[0].lower()
            assert "WScript.Shell" in ps_cmd[-1]
        finally:
            patch.stopall()

    def test_create_shortcut_calledprocesserror(self, monkeypatch):
        """PowerShell 调用失败时返回 False。"""
        import subprocess
        with patch.object(subprocess, "run",
                          side_effect=subprocess.CalledProcessError(1, "ps")):
            from net_monitor import _create_shortcut
            assert _create_shortcut("a", "b") is False


class TestApiKeyDialog:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_creation_empty(self):
        from net_monitor import ApiKeyDialog
        d = ApiKeyDialog()
        assert d.windowTitle() == "设置 DeepSeek API Key"
        assert d.key_value() == ""

    def test_creation_with_key(self):
        from net_monitor import ApiKeyDialog
        d = ApiKeyDialog(current_key="sk-existing")
        assert d.key_value() == "sk-existing"

    def test_whitespace_trimmed(self):
        from net_monitor import ApiKeyDialog
        d = ApiKeyDialog(current_key="  sk-spaces  ")
        assert d.key_value() == "sk-spaces"


class TestStatsDialog:
    @pytest.fixture(autouse=True)
    def qapp_fixture(self, qapp):
        return qapp

    def test_creation(self):
        from net_monitor import StatsDialog
        d = StatsDialog()
        assert d.windowTitle() == "流量统计"

    def test_update_stats(self):
        from net_monitor import StatsDialog
        d = StatsDialog()
        d.update_stats(1_000_000, 2_000_000, 50_000_000, 100_000_000, "WLAN")

    def test_update_zero(self):
        from net_monitor import StatsDialog
        d = StatsDialog()
        d.update_stats(0, 0, 0, 0)

    def test_update_no_nic(self):
        from net_monitor import StatsDialog
        d = StatsDialog()
        d.update_stats(100, 200, 1000, 2000)
