"""
net_monitor.py — 网络流量监控悬浮窗 主程序入口

启动方式:
    pythonw net_monitor.py    (无黑窗，推荐)
    python  net_monitor.py    (有控制台窗口)
"""

import sys
import os
from pathlib import Path

# 抑制 Qt 无害字体警告（如 EUDC.TTE 缺失）
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QDialog, QVBoxLayout, QLabel,
    QLineEdit, QCheckBox, QDialogButtonBox,
)

from net_store import StatsStore, ConfigStore
from net_engine import NetEngine, format_bytes
from net_deepseek import DeepSeekBalanceChecker, BalanceInfo, DeepSeekError
from overlay import Overlay, WINDOW_WIDTH, WINDOW_HEIGHT
from net_tray import TrayIcon
from input_counter import InputCounter

# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------

# PyInstaller 兼容：打包后 __file__ 指向临时目录，改用 exe 所在目录
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LNK_NAME = "NetMonitor.lnk"

SAVE_INTERVAL = 10  # 每 N 秒保存一次统计和配置


# ------------------------------------------------------------------
# 开机自启管理（使用 Windows 快捷方式，无编码问题）
# ------------------------------------------------------------------

def _get_pythonw_path() -> str:
    """获取 pythonw.exe 的完整路径。打包为 EXE 时返回自身。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        return exe[:-10] + "pythonw.exe"
    return exe


def _startup_lnk_path() -> Path:
    return STARTUP_DIR / LNK_NAME


def _create_shortcut(target: str, shortcut_path: str,
                     arguments: str = "", working_dir: str = "") -> bool:
    """通过 PowerShell 创建 Windows 快捷方式 (.lnk)。"""
    import subprocess

    def _escape_ps(s: str) -> str:
        """转义 PowerShell 单引号字符串中的单引号。"""
        return s.replace("'", "''")

    ps = (
        f"$s = (New-Object -ComObject WScript.Shell)"
        f".CreateShortcut('{_escape_ps(shortcut_path)}');"
        f"$s.TargetPath = '{_escape_ps(target)}';"
        f"$s.Arguments = '{_escape_ps(arguments)}';"
        f"$s.WorkingDirectory = '{_escape_ps(working_dir)}';"
        f"$s.WindowStyle = 7;"
        f"$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, timeout=10, check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def autostart_is_enabled() -> bool:
    return _startup_lnk_path().exists()


def autostart_enable() -> bool:
    """在 Startup 文件夹创建快捷方式。"""
    try:
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        pythonw = _get_pythonw_path()
        if getattr(sys, "frozen", False):
            # 打包为 EXE：直接指向 EXE，无需额外参数
            return _create_shortcut(
                target=pythonw,
                shortcut_path=str(_startup_lnk_path()),
                working_dir=str(BASE_DIR),
            )
        else:
            script = str(BASE_DIR / "net_monitor.py")
            return _create_shortcut(
                target=pythonw,
                shortcut_path=str(_startup_lnk_path()),
                arguments=f'"{script}"',
                working_dir=str(BASE_DIR),
            )
    except OSError:
        return False


def autostart_disable() -> bool:
    """删除 Startup 文件夹中的快捷方式。"""
    try:
        p = _startup_lnk_path()
        if p.exists():
            p.unlink()
        return True
    except OSError:
        return False


def autostart_sync(enable: bool) -> bool:
    """根据开关状态同步自启文件。"""
    if enable:
        return autostart_enable()
    else:
        return autostart_disable()


# ------------------------------------------------------------------
# DeepSeek API Key 输入对话框
# ------------------------------------------------------------------

class ApiKeyDialog(QDialog):
    """DeepSeek API Key 输入对话框。"""

    def __init__(self, current_key: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置 DeepSeek API Key")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint
        )
        self.setFixedSize(420, 170)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # 说明文字
        hint = QLabel(
            "请输入 DeepSeek API Key：\n"
            "（Key 将以明文存储在 config.json 中，请注意安全）"
        )
        hint.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(hint)

        # 输入框
        self._input = QLineEdit()
        self._input.setPlaceholderText("sk-...")
        self._input.setEchoMode(QLineEdit.Password)
        if current_key:
            self._input.setText(current_key)
        layout.addWidget(self._input)

        # 显示/隐藏切换
        self._show_cb = QCheckBox("显示 API Key")
        self._show_cb.toggled.connect(self._on_show_toggled)
        layout.addWidget(self._show_cb)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog {
                background: #fff;
                border: 1px solid #ddd;
                border-radius: 6px;
            }
            QLineEdit {
                padding: 6px 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
        """)

    def _on_show_toggled(self, checked: bool):
        self._input.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )

    def key_value(self) -> str:
        """返回用户输入的 API Key（去除首尾空白）。"""
        return self._input.text().strip()


# ------------------------------------------------------------------
# 统计弹窗
# ------------------------------------------------------------------

class StatsDialog(QDialog):
    """流量统计详情弹窗。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("流量统计")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint
        )
        self.setFixedSize(280, 230)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 16, 20, 16)

        self._today_label = QLabel()
        self._month_label = QLabel()
        self._nic_label = QLabel()
        self._balance_total_label = QLabel()
        self._balance_granted_label = QLabel()
        self._balance_topped_label = QLabel()

        for lbl in [self._today_label, self._month_label, self._nic_label]:
            lbl.setStyleSheet("font-size: 13px; color: #333;")
            layout.addWidget(lbl)

        # 分隔线
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #eee;")
        layout.addWidget(sep)

        for lbl in [self._balance_total_label, self._balance_granted_label,
                     self._balance_topped_label]:
            lbl.setStyleSheet("font-size: 12px; color: #555;")
            layout.addWidget(lbl)

        self.setStyleSheet("""
            QDialog {
                background: #fff;
                border: 1px solid #ddd;
                border-radius: 6px;
            }
        """)

    def update_stats(self, today_tx: int, today_rx: int,
                     month_tx: int, month_rx: int, nic_name: str = "",
                     balance: BalanceInfo | None = None,
                     balance_error: str | None = None) -> None:
        self._today_label.setText(
            f"<b>今日流量</b>  ▲ {format_bytes(today_tx)}  ▼ {format_bytes(today_rx)}"
        )
        self._month_label.setText(
            f"<b>本月流量</b>  ▲ {format_bytes(month_tx)}  ▼ {format_bytes(month_rx)}"
        )
        self._nic_label.setText(f"<b>监控网卡</b>  {nic_name or '—'}")

        if balance is not None:
            self._balance_total_label.setText(
                f"<b>DeepSeek 总余额</b>  {balance.currency} {balance.total_balance}"
            )
            self._balance_granted_label.setText(
                f"<b>赠送余额</b>  {balance.currency} {balance.granted_balance}"
            )
            self._balance_topped_label.setText(
                f"<b>充值余额</b>  {balance.currency} {balance.topped_up_balance}"
            )
        elif balance_error:
            self._balance_total_label.setText(
                f"<b>DeepSeek</b>  <span style='color:#f44336;'>{balance_error}</span>"
            )
            self._balance_granted_label.setText("")
            self._balance_topped_label.setText("")
        else:
            self._balance_total_label.setText("<b>DeepSeek</b>  未配置 API Key")
            self._balance_granted_label.setText("")
            self._balance_topped_label.setText("")


# ------------------------------------------------------------------
# 主程序
# ------------------------------------------------------------------

class NetMonitor:
    """网络流量监控主控制器。"""

    def __init__(self):
        self._store = StatsStore()
        self._config = ConfigStore()
        self._engine = NetEngine(store=self._store)
        self._balance_checker = DeepSeekBalanceChecker(config=self._config)
        self._input_counter = InputCounter()
        self._overlay: Overlay | None = None
        self._tray: TrayIcon | None = None
        self._stats_dialog: StatsDialog | None = None
        self._timer = QTimer()
        self._save_counter = 0

    def run(self) -> None:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName("NetMonitor")

        # --- 初始化网卡 ---
        if not self._engine.init(preferred_nic=self._config.nic_name):
            QMessageBox.warning(None, "网络监控", "未能检测到活动网络接口，请检查网络连接。")
            # 不退出，让用户有机会手动设置

        # --- 创建 UI ---
        self._overlay = Overlay()
        self._tray = TrayIcon()

        # 窗口初始位置
        x, y = self._config.get_window_pos()
        if x is not None and y is not None:
            # 验证是否在屏幕内
            screen = app.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = max(0, min(x, geo.width() - WINDOW_WIDTH))
                y = max(0, min(y, geo.height() - WINDOW_HEIGHT))
            self._overlay.move(x, y)
        else:
            # 默认右下角
            screen = app.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self._overlay.move(
                    geo.width() - WINDOW_WIDTH - 20,
                    geo.height() - WINDOW_HEIGHT - 60,
                )

        self._overlay.show()

        # --- 初始开关状态 ---
        if not self._config.show_deepseek_balance:
            self._overlay.set_show_balance(False)
        if not self._config.show_input_counter:
            self._overlay.set_show_input(False)

        # --- 托盘图标 ---
        self._tray.show()

        # --- 连接信号 ---
        self._setup_connections()

        # --- 自启动状态 ---
        self._sync_autostart_ui()

        # --- 首次尝试开机自启 ---
        if not self._config.autostart and not autostart_is_enabled():
            # 首次运行，询问是否开启自启
            reply = QMessageBox.question(
                None, "开机自启",
                "是否开启开机自启动？\n(后续可在悬浮窗或托盘菜单中修改)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._toggle_autostart(True)
        elif self._config.autostart and not autostart_is_enabled():
            # config 说开了但文件丢了，补上
            autostart_enable()

        # --- 定时器 ---
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(1000)  # 每秒

        # --- 输入计数器（跟随开关状态）---
        self._input_counter.load_counts(
            self._config.saved_key_count,
            self._config.saved_click_count,
        )
        if self._config.show_input_counter:
            self._input_counter.start()

        # --- 事件循环 ---
        try:
            app.exec_()
        finally:
            self._on_exit()

    # ------------------------------------------------------------------
    # 连接设置
    # ------------------------------------------------------------------

    def _setup_connections(self):
        o = self._overlay
        t = self._tray

        # 悬浮窗右键菜单
        o.quit_action.triggered.connect(self._quit)
        o.hide_action.triggered.connect(o.hide)
        o.autostart_action.triggered.connect(self._toggle_autostart)
        o.show_stats_action.triggered.connect(self._show_stats)
        o.set_api_key_action.triggered.connect(self._show_api_key_dialog)
        o.show_balance_action.toggled.connect(self._toggle_show_balance)
        o.show_input_action.toggled.connect(self._toggle_show_input)

        # 拖拽移动后保存位置
        o.set_moved_callback(self._on_window_moved)

        # 托盘菜单
        t.quit_action.triggered.connect(self._quit)
        t.autostart_action.triggered.connect(self._toggle_autostart)
        t.show_action.triggered.connect(self._toggle_visibility)
        t.set_api_key_action.triggered.connect(self._show_api_key_dialog)

    # ------------------------------------------------------------------
    # 定时回调
    # ------------------------------------------------------------------

    def _on_tick(self):
        ok = self._engine.tick()
        if not ok:
            return

        rate = self._engine.rate

        # 余额查询（后台线程，不阻塞 UI）
        if self._config.show_deepseek_balance:
            self._balance_checker.try_refresh()
            self._balance_checker.poll()

        # 缓存当日/当月统计（避免重复计算日期键）
        today = self._store.get_today()
        month = self._store.get_month()

        # 更新悬浮窗
        self._overlay.update_data(
            history=self._engine.history,
            tx_rate=rate.tx,
            rx_rate=rate.rx,
            today_tx=today["tx"],
            today_rx=today["rx"],
            month_tx=month["tx"],
            month_rx=month["rx"],
        )

        # 更新悬浮窗余额文本
        if self._config.show_deepseek_balance:
            self._update_overlay_balance()

        # 更新输入计数
        if self._config.show_input_counter:
            self._overlay.update_input_counts(
                self._input_counter.key_count,
                self._input_counter.click_count,
            )

        # 更新托盘图标
        self._tray.update_speed(rate.tx, rate.rx)

        # 更新统计弹窗（如果打开）
        if self._stats_dialog and self._stats_dialog.isVisible():
            self._stats_dialog.update_stats(
                today["tx"], today["rx"],
                month["tx"], month["rx"],
                self._engine.nic_name or "",
                balance=self._balance_checker.balance,
                balance_error=self._balance_checker.last_error,
            )

        # 定期保存
        self._save_counter += 1
        if self._save_counter >= SAVE_INTERVAL:
            self._save_counter = 0
            self._store.save()
            self._config.nic_name = self._engine.nic_name
            k, c = self._input_counter.snapshot()
            self._config.saved_key_count = k
            self._config.saved_click_count = c
            self._config.save()

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    def _toggle_autostart(self, enable: bool | None = None) -> None:
        if enable is None:
            enable = not autostart_is_enabled()
        ok = autostart_sync(enable)
        if ok:
            self._config.autostart = enable
            self._config.save()
        self._sync_autostart_ui()

    def _toggle_show_balance(self, checked: bool) -> None:
        """切换 DeepSeek 余额显示（关闭后 _on_tick 自动停止 API 请求）。"""
        self._config.show_deepseek_balance = checked
        self._config.save()
        self._overlay.set_show_balance(checked)

    def _toggle_show_input(self, checked: bool) -> None:
        """切换键盘鼠标计数显示。"""
        self._config.show_input_counter = checked
        self._config.save()
        self._overlay.set_show_input(checked)
        if checked:
            self._input_counter.start()
        else:
            self._input_counter.stop()

    def _sync_autostart_ui(self):
        state = autostart_is_enabled()
        self._overlay.set_autostart_checked(state)
        self._tray.set_autostart_checked(state)

    def _toggle_visibility(self):
        if self._overlay.isVisible():
            self._overlay.hide()
        else:
            self._overlay.show()

    def _update_overlay_balance(self):
        """将从 checker 拿到余额状态转换为 overlay 可显示的文本。"""
        b = self._balance_checker.balance
        err = self._balance_checker.last_error

        if b is not None:
            self._overlay.update_balance(
                text=f"DS {b.currency} {b.total_balance}",
                has_error=False,
            )
        elif err is not None:
            self._overlay.update_balance(text=err, has_error=True)
        elif self._balance_checker.is_configured():
            self._overlay.update_balance(text="DS ...", has_error=False)
        else:
            self._overlay.update_balance(None)  # 未配置，不显示

    def _show_api_key_dialog(self):
        """弹出 API Key 输入对话框。"""
        dialog = ApiKeyDialog(
            current_key=self._config.deepseek_api_key,
        )
        if dialog.exec_() == QDialog.Accepted:
            self._config.deepseek_api_key = dialog.key_value()
            self._config.save()
            self._balance_checker.reset()
            # 立即使余额文本同步
            self._update_overlay_balance()

    def _show_stats(self):
        if self._stats_dialog is None:
            self._stats_dialog = StatsDialog()
        self._stats_dialog.update_stats(
            self._store.get_today()["tx"],
            self._store.get_today()["rx"],
            self._store.get_month()["tx"],
            self._store.get_month()["rx"],
            self._engine.nic_name or "",
            balance=self._balance_checker.balance,
            balance_error=self._balance_checker.last_error,
        )
        self._stats_dialog.show()
        self._stats_dialog.raise_()

    def _on_window_moved(self):
        if self._overlay:
            pos = self._overlay.pos()
            self._config.set_window_pos(pos.x(), pos.y())

    def _quit(self):
        self._on_exit()
        QApplication.instance().quit()

    def _on_exit(self):
        """程序退出时保存数据。"""
        k, c = self._input_counter.snapshot()
        self._config.saved_key_count = k
        self._config.saved_click_count = c
        self._input_counter.stop()
        self._store.save()
        if self._overlay:
            pos = self._overlay.pos()
            self._config.set_window_pos(pos.x(), pos.y())
        self._config.nic_name = self._engine.nic_name
        self._config.save()


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------

if __name__ == "__main__":
    # 拦截控制台关闭事件：关闭命令行窗口不会终止悬浮窗
    # （Ctrl+C 仍然可以正常终止程序）
    if sys.platform == "win32":
        import ctypes
        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        def _console_ctrl_handler(event):
            # CTRL_CLOSE_EVENT = 2，返回 True 阻止进程被终止
            return event == 2
        ctypes.windll.kernel32.SetConsoleCtrlHandler(
            _console_ctrl_handler, True,
        )
    monitor = NetMonitor()
    monitor.run()
