"""
net_tray.py — 系统托盘图标渲染

在 16×16 图标上绘制压缩格式的两行文本:
  ↑1.2M  (绿色, 上行)
  ↓0.8M  (蓝色, 下行)
"""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter, QPixmap, QIcon, QColor, QFont, QPen
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction

# ------------------------------------------------------------------
# 颜色定义
# ------------------------------------------------------------------

COLOR_TX = QColor("#4CAF50")   # 上行：绿色
COLOR_RX = QColor("#2196F3")   # 下行：蓝色
COLOR_BG = QColor(0, 0, 0, 0)  # 透明背景


def render_tray_icon(tx_text: str, rx_text: str, size: int = 16) -> QIcon:
    """根据上下行速度文字渲染托盘图标。

    Args:
        tx_text: 上行文本，如 "1.2M"
        rx_text: 下行文本，如 "0.8K"
        size: 图标像素大小，默认 16。
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    # 字体
    font = QFont("Microsoft YaHei", 6)
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, -0.5)

    # 绘制上行 (绿色，上半)
    painter.setFont(font)
    painter.setPen(QPen(COLOR_TX))
    painter.drawText(0, 0, size, size // 2, Qt.AlignCenter | Qt.AlignBottom, f"▲{tx_text}")

    # 绘制下行 (蓝色，下半)
    painter.setPen(QPen(COLOR_RX))
    painter.drawText(0, size // 2, size, size // 2, Qt.AlignCenter | Qt.AlignTop, f"▼{rx_text}")

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """系统托盘图标，支持实时更新上下行速度显示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tx_text = "0"
        self._rx_text = "0"
        self._size = 16

        # 初始图标
        self._update_icon()

        # 右键菜单
        self._menu = QMenu()
        self._show_action = QAction("显示/隐藏悬浮窗")
        self._set_api_key_action = QAction("设置 DeepSeek API Key")
        self._autostart_action = QAction("开机自启")
        self._autostart_action.setCheckable(True)
        self._quit_action = QAction("退出")

        self._menu.addAction(self._show_action)
        self._menu.addSeparator()
        self._menu.addAction(self._set_api_key_action)
        self._menu.addAction(self._autostart_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self.setContextMenu(self._menu)

        # 左键点击显示/隐藏悬浮窗
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def update_speed(self, tx_bytes: float, rx_bytes: float) -> None:
        """更新显示的网速。

        Args:
            tx_bytes: 上行速率 bytes/s
            rx_bytes: 下行速率 bytes/s
        """
        from net_engine import format_tray_speed
        self._tx_text = format_tray_speed(tx_bytes)
        self._rx_text = format_tray_speed(rx_bytes)
        self._update_icon()

    @property
    def show_action(self):
        return self._show_action

    @property
    def set_api_key_action(self):
        return self._set_api_key_action

    @property
    def autostart_action(self):
        return self._autostart_action

    @property
    def quit_action(self):
        return self._quit_action

    def set_autostart_checked(self, val: bool) -> None:
        self._autostart_action.setChecked(val)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_icon(self) -> None:
        icon = render_tray_icon(self._tx_text, self._rx_text, self._size)
        self.setIcon(icon)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_action.trigger()
