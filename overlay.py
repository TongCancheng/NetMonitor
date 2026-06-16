"""
overlay.py — 透明悬浮窗 UI

- 无边框、始终置顶、透明背景
- QPainter 绘制波形图 + 网速文本
- 左键拖拽移动、右键菜单
"""

from collections import deque
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QBrush,
    QLinearGradient, QFontMetrics,
)
from PyQt5.QtWidgets import QWidget, QMenu, QAction, QApplication


# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------

WINDOW_WIDTH = 200
WINDOW_HEIGHT = 95

# 背景
BG_COLOR = QColor(240, 240, 240, 200)  # 浅灰半透明
BG_RADIUS = 10                          # 圆角半径

COLOR_TX = QColor("#4CAF50")        # 上行：绿
COLOR_RX = QColor("#2196F3")        # 下行：蓝
COLOR_TX_FILL = QColor(76, 175, 80, 40)
COLOR_RX_FILL = QColor(33, 150, 243, 40)
COLOR_TEXT = QColor(255, 255, 255)
COLOR_TEXT_SHADOW = QColor(0, 0, 0, 160)
COLOR_GRID = QColor(180, 180, 180, 60)  # 网格线（浅灰背景上可见）

# 布局常量
CHART_LEFT = 4
CHART_TOP = 34
CHART_RIGHT = WINDOW_WIDTH - 4
CHART_BOTTOM = WINDOW_HEIGHT - 4

TEXT_LEFT = 8
TEXT_TOP_TX = 5
TEXT_TOP_RX = 23
TEXT_RIGHT_MARGIN = 8


class Overlay(QWidget):
    """透明悬浮窗。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # 窗口尺寸
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # 数据
        self._history: deque = deque(maxlen=60)  # [(tx_bps, rx_bps), ...]
        self._tx_rate = 0.0
        self._rx_rate = 0.0
        self._today_tx = 0
        self._today_rx = 0
        self._month_tx = 0
        self._month_rx = 0

        # 余额显示状态
        self._balance_text: str | None = None   # "CNY 110.00" 或错误文本
        self._balance_error: bool = False

        # 输入计数
        self._key_count: int = 0
        self._click_count: int = 0
        self._show_input: bool = True

        # 余额显示开关
        self._show_balance: bool = True

        # 拖拽状态
        self._dragging = False
        self._drag_offset = QPoint()
        self._on_moved_callback = None

        # 右键菜单
        self._setup_menu()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def update_data(
        self,
        history: deque,
        tx_rate: float,
        rx_rate: float,
        today_tx: int = 0,
        today_rx: int = 0,
        month_tx: int = 0,
        month_rx: int = 0,
    ) -> None:
        """更新显示数据并触发重绘。"""
        self._history = history
        self._tx_rate = tx_rate
        self._rx_rate = rx_rate
        self._today_tx = today_tx
        self._today_rx = today_rx
        self._month_tx = month_tx
        self._month_rx = month_rx
        self.update()

    def set_moved_callback(self, cb) -> None:
        """设置拖拽结束后的回调（保存窗口位置等）。"""
        self._on_moved_callback = cb

    def update_balance(self, text: str | None, has_error: bool = False) -> None:
        """更新 DeepSeek 余额文本显示。text=None 时不显示。"""
        self._balance_text = text
        self._balance_error = has_error
        self.update()

    def update_input_counts(self, key_count: int, click_count: int) -> None:
        """更新键盘 / 鼠标点击计数。"""
        if self._key_count == key_count and self._click_count == click_count:
            return  # 无变化，跳过重绘
        self._key_count = key_count
        self._click_count = click_count
        self.update()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        self._draw_background(painter)
        self._draw_waveform(painter)
        self._draw_speed_text(painter)
        self._draw_balance(painter)
        self._draw_input_counts(painter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            if self._on_moved_callback:
                self._on_moved_callback()

    def contextMenuEvent(self, event):
        self._menu.popup(event.globalPos())

    def closeEvent(self, event):
        # 不退出，隐藏到托盘
        event.ignore()
        self.hide()

    # ------------------------------------------------------------------
    # 内部绘制
    # ------------------------------------------------------------------

    def _draw_background(self, painter: QPainter):
        """绘制浅灰色半透明圆角背景。"""
        path = QPainterPath()
        path.addRoundedRect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT,
                           BG_RADIUS, BG_RADIUS)
        painter.fillPath(path, BG_COLOR)

    def _draw_waveform(self, painter: QPainter):
        if len(self._history) < 2:
            return

        data = list(self._history)
        n = len(data)
        chart_w = CHART_RIGHT - CHART_LEFT
        chart_h = CHART_BOTTOM - CHART_TOP

        # --- 计算 Y 轴范围 ---
        max_val = 0.0
        for tx, rx in data:
            max_val = max(max_val, tx, rx)
        if max_val < 1:
            max_val = 1
        max_val = self._nice_ceil(max_val)
        mid_val = max_val / 2

        # --- X 坐标映射 ---
        def x_of(i):
            if n > 1:
                return CHART_LEFT + i / (n - 1) * (chart_w - 1)
            return CHART_LEFT

        # --- Y 坐标映射 ---
        def y_of(v):
            return CHART_BOTTOM - (v / max_val) * (chart_h - 1)

        # --- 绘制微弱参考线 ---
        pen_grid = QPen(COLOR_GRID, 0.5, Qt.DotLine)
        painter.setPen(pen_grid)
        for ref_y_val in [mid_val, max_val]:
            ref_y = y_of(ref_y_val)
            painter.drawLine(QPoint(CHART_LEFT, int(ref_y)),
                           QPoint(CHART_RIGHT - 1, int(ref_y)))

        # --- 上行波形填充 ---
        tx_path = QPainterPath()
        tx_path.moveTo(x_of(0), y_of(data[0][0]))
        for i in range(1, n):
            tx_path.lineTo(x_of(i), y_of(data[i][0]))
        tx_path.lineTo(x_of(n - 1), CHART_BOTTOM)
        tx_path.lineTo(x_of(0), CHART_BOTTOM)
        tx_path.closeSubpath()
        painter.fillPath(tx_path, COLOR_TX_FILL)

        # --- 下行波形填充 ---
        rx_path = QPainterPath()
        rx_path.moveTo(x_of(0), y_of(data[0][1]))
        for i in range(1, n):
            rx_path.lineTo(x_of(i), y_of(data[i][1]))
        rx_path.lineTo(x_of(n - 1), CHART_BOTTOM)
        rx_path.lineTo(x_of(0), CHART_BOTTOM)
        rx_path.closeSubpath()
        painter.fillPath(rx_path, COLOR_RX_FILL)

        # --- 绘制折线 ---
        pen_tx = QPen(COLOR_TX, 1.5)
        painter.setPen(pen_tx)
        for i in range(1, n):
            painter.drawLine(
                QPoint(int(x_of(i - 1)), int(y_of(data[i - 1][0]))),
                QPoint(int(x_of(i)), int(y_of(data[i][0]))),
            )

        pen_rx = QPen(COLOR_RX, 1.5)
        painter.setPen(pen_rx)
        for i in range(1, n):
            painter.drawLine(
                QPoint(int(x_of(i - 1)), int(y_of(data[i - 1][1]))),
                QPoint(int(x_of(i)), int(y_of(data[i][1]))),
            )

    # ------------------------------------------------------------------
    # 共享绘制工具
    # ------------------------------------------------------------------

    def _draw_label(
        self,
        painter: QPainter,
        text: str,
        y: int,
        color: QColor,
        font: QFont,
        alignment: Qt.AlignmentFlag,
    ) -> None:
        """绘制带阴影的标签文本。"""
        text_w = WINDOW_WIDTH - TEXT_LEFT - TEXT_RIGHT_MARGIN
        text_h = 16

        painter.setFont(font)
        painter.setPen(COLOR_TEXT_SHADOW)
        painter.drawText(TEXT_LEFT + 1, y + 1, text_w, text_h, alignment, text)
        painter.setPen(color)
        painter.drawText(TEXT_LEFT, y, text_w, text_h, alignment, text)

    # ------------------------------------------------------------------
    # 绘制各部分
    # ------------------------------------------------------------------

    def _draw_speed_text(self, painter: QPainter):
        """绘制网速文本（左上角）。"""
        from net_engine import format_speed

        font = QFont("Microsoft YaHei", 10, QFont.Bold)
        left = Qt.AlignLeft | Qt.AlignVCenter

        self._draw_label(painter, f"▲{format_speed(self._tx_rate)}",
                         TEXT_TOP_TX, COLOR_TX, font, left)
        self._draw_label(painter, f"▼{format_speed(self._rx_rate)}",
                         TEXT_TOP_RX, COLOR_RX, font, left)

    def _draw_balance(self, painter: QPainter):
        """绘制 DeepSeek 余额文本（右上角）。"""
        if not self._show_balance or self._balance_text is None:
            return

        font = QFont("Microsoft YaHei", 9, QFont.Bold)
        right = Qt.AlignRight | Qt.AlignVCenter
        color = QColor("#f44336") if self._balance_error else QColor("#FFD700")

        self._draw_label(painter, self._balance_text, TEXT_TOP_TX,
                         color, font, right)

    def _draw_input_counts(self, painter: QPainter):
        """绘制键盘 / 鼠标点击计数（RX 行右侧）。"""
        if not self._show_input:
            return
        font = QFont("Microsoft YaHei", 8, QFont.Normal)
        right = Qt.AlignRight | Qt.AlignVCenter
        color = QColor(100, 100, 100)

        text = f"K:{self._key_count}  M:{self._click_count}"
        self._draw_label(painter, text, TEXT_TOP_RX, color, font, right)

    def _setup_menu(self):
        self._menu = QMenu(self)

        self._show_stats_action = QAction("查看流量统计")
        self._set_api_key_action = QAction("设置 DeepSeek API Key")
        self._show_balance_action = QAction("显示 DeepSeek 余额")
        self._show_balance_action.setCheckable(True)
        self._show_balance_action.setChecked(self._show_balance)
        self._show_input_action = QAction("显示键盘鼠标计数")
        self._show_input_action.setCheckable(True)
        self._show_input_action.setChecked(self._show_input)
        self._autostart_action = QAction("开机自启")
        self._autostart_action.setCheckable(True)
        self._hide_action = QAction("隐藏到托盘")
        self._quit_action = QAction("退出")

        self._menu.addAction(self._show_stats_action)
        self._menu.addAction(self._set_api_key_action)
        self._menu.addAction(self._show_balance_action)
        self._menu.addAction(self._show_input_action)
        self._menu.addSeparator()
        self._menu.addAction(self._autostart_action)
        self._menu.addAction(self._hide_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

    # ------------------------------------------------------------------
    # 菜单动作属性
    # ------------------------------------------------------------------

    @property
    def set_api_key_action(self):
        return self._set_api_key_action

    @property
    def show_balance_action(self):
        return self._show_balance_action

    @property
    def show_input_action(self):
        return self._show_input_action

    @property
    def show_stats_action(self):
        return self._show_stats_action

    @property
    def autostart_action(self):
        return self._autostart_action

    @property
    def hide_action(self):
        return self._hide_action

    @property
    def quit_action(self):
        return self._quit_action

    def set_autostart_checked(self, val: bool) -> None:
        self._autostart_action.setChecked(val)

    def set_show_balance(self, val: bool) -> None:
        """设置是否显示 DeepSeek 余额。"""
        self._show_balance = val
        self._show_balance_action.setChecked(val)
        if not val:
            self._balance_text = None
        self.update()

    def set_show_input(self, val: bool) -> None:
        """设置是否显示键盘鼠标计数。"""
        self._show_input = val
        self._show_input_action.setChecked(val)
        self.update()

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------

    @staticmethod
    def _nice_ceil(v: float) -> float:
        """将数值向上取整到漂亮的刻度。"""
        if v <= 0:
            return 1
        import math
        mag = 10 ** math.floor(math.log10(v))
        candidate = mag
        while candidate < v:
            candidate += mag
        if candidate < v * 1.1:
            candidate += mag
        return candidate
