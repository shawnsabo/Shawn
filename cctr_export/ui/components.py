"""UI 组件库"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QProgressBar, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from .theme import Colors


class Card(QFrame):
    """圆角卡片容器（带阴影）"""
    def __init__(self, parent=None, radius: int = 12, padding: int = 20, shadow: bool = True):
        super().__init__(parent)
        self._radius = radius
        self.setObjectName("Card")
        self.setStyleSheet(f"""
            #Card {{
                background: {Colors.CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: {radius}px;
            }}
        """)
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(16)
            effect.setColor(QColor(Colors.SHADOW + "44"))
            effect.setOffset(0, 4)
            self.setGraphicsEffect(effect)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(padding, padding, padding, padding)
        self._layout = layout

    def addWidget(self, widget):
        self._layout.addWidget(widget)

    def addLayout(self, layout):
        self._layout.addLayout(layout)

    def layout(self):
        return self._layout


class StatusBadge(QLabel):
    """状态徽章"""
    STYLES = {
        "waiting": ("⏳ 等待", Colors.WARNING),
        "processing": ("⚙️ 进行中", Colors.INFO),
        "success": ("✅ 成功", Colors.SUCCESS),
        "failed": ("❌ 失败", Colors.ERROR),
    }

    def __init__(self, status: str, parent=None):
        text, color = self.STYLES.get(status, (status, "#8b949e"))
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            background: {color}22;
            color: {color};
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        """)
        self.setFixedHeight(28)


class SpinningIndicator(QWidget):
    """加载动画"""
    def __init__(self, parent=None, size=32):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = self.startTimer(50)

    def timerEvent(self, event):
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(Colors.ACCENT), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.drawArc(rect, self._angle * 16, 270 * 16)
        painter.end()

    def stop(self):
        if self._timer:
            self.killTimer(self._timer)
            self._timer = None


class SectionTitle(QLabel):
    """段落标题"""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            font-size: 20px;
            font-weight: 700;
            color: {Colors.TEXT_PRIMARY};
            padding: 4px 0;
        """)


class EmptyState(QWidget):
    """空状态提示"""
    def __init__(self, icon: str = "📭", text: str = "暂无数据", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size: 56px;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_text = QLabel(text)
        lbl_text.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 15px;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_icon)
        layout.addWidget(lbl_text)


class FABButton(QPushButton):
    """浮动操作按钮"""
    def __init__(self, icon: str = "＋", parent=None):
        super().__init__(icon, parent)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(Colors.ACCENT + "88"))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT};
                color: white;
                border: none;
                border-radius: 28px;
                font-size: 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT_HOVER};
            }}
        """)


class TaskCard(QFrame):
    """任务卡片（用于主页，带阴影）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskCard")
        self.setStyleSheet(f"""
            #TaskCard {{
                background: {Colors.CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 12px;
                padding: 2px;
            }}
            #TaskCard:hover {{
                border-color: {Colors.ACCENT}44;
                background: {Colors.CARD_HOVER};
            }}
        """)
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(12)
        effect.setColor(QColor(Colors.SHADOW + "33"))
        effect.setOffset(0, 3)
        self.setGraphicsEffect(effect)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(10)

    def addWidget(self, w):
        self._layout.addWidget(w)

    def addLayout(self, l):
        self._layout.addLayout(l)

    def layout(self):
        return self._layout


class StepIndicator(QWidget):
    """步骤指示器 - 带脉冲动画"""
    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self._steps = steps
        self._current = 0
        self.setFixedHeight(80)
        self._step_colors = {
            "done": Colors.SUCCESS,
            "active": Colors.ACCENT,
            "pending": Colors.BORDER,
        }
        self._pulse = 0
        self._pulse_dir = 1
        # 脉冲动画
        from PySide6.QtCore import QTimer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(40)

    def _update_pulse(self):
        self._pulse += 0.08 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse = 1.0
            self._pulse_dir = -1
        elif self._pulse <= 0.0:
            self._pulse = 0.0
            self._pulse_dir = 1
        if self._current < len(self._steps):
            self.update()

    def set_step(self, index: int):
        self._current = index
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        n = len(self._steps)
        if n == 0:
            return

        # 居中布局
        label_y_center = h // 2 + 4
        circle_y_center = h // 2 - 16
        label_y = circle_y_center + 28

        # 自适应左右边距
        label_width = max(100, w // n - 20)
        total_content_w = n * label_width + (n - 1) * 20
        start_x = (w - total_content_w) // 2

        for i in range(n):
            cx = start_x + i * (label_width + 20) + label_width // 2

            # 连接线（两条线之间）
            if i > 0:
                prev_cx = start_x + (i - 1) * (label_width + 20) + label_width // 2
                line_color = self._step_colors["done"] if i <= self._current else self._step_colors["pending"]
                painter.setPen(QPen(QColor(line_color), 2.5))
                painter.drawLine(prev_cx + 12, circle_y_center, cx - 12, circle_y_center)

            # 圆半径
            r = 14

            if i < self._current:
                # 已完成：绿色实心圆 + ✓
                painter.setBrush(QColor(self._step_colors["done"]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(cx - r, circle_y_center - r, r * 2, r * 2)
                font = painter.font()
                font.setPixelSize(14)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(cx - r, circle_y_center - r, r * 2, r * 2,
                                 Qt.AlignmentFlag.AlignCenter, "✓")
            elif i == self._current:
                # 当前：蓝色大圆 + 数字 + 脉冲外发光
                r_active = 16
                # 脉冲外圈（半透明渐变感）
                glow_alpha = int(80 + 80 * self._pulse)
                glow_color = QColor(Colors.ACCENT)
                glow_color.setAlpha(glow_alpha)
                pen = QPen(glow_color, 3)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                glow_r = r_active + 5 + int(3 * self._pulse)
                painter.drawEllipse(cx - glow_r, circle_y_center - glow_r, glow_r * 2, glow_r * 2)

                # 实心圆
                painter.setBrush(QColor(self._step_colors["active"]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(cx - r_active, circle_y_center - r_active, r_active * 2, r_active * 2)

                font = painter.font()
                font.setPixelSize(13)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(cx - r_active, circle_y_center - r_active, r_active * 2, r_active * 2,
                                 Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                # 未完成：灰色边框圆
                painter.setBrush(QColor(Colors.BG))
                pen = QPen(QColor(self._step_colors["pending"]), 2)
                painter.setPen(pen)
                painter.drawEllipse(cx - r, circle_y_center - r, r * 2, r * 2)
                font = painter.font()
                font.setPixelSize(12)
                painter.setFont(font)
                painter.setPen(QColor(Colors.TEXT_SECONDARY))
                painter.drawText(cx - r, circle_y_center - r, r * 2, r * 2,
                                 Qt.AlignmentFlag.AlignCenter, str(i + 1))

            # 标签（圆下方）
            font = painter.font()
            font.setPixelSize(13)
            font.setBold(i == self._current)
            painter.setFont(font)
            label_color = self._step_colors["active"] if i == self._current else (self._step_colors["done"] if i < self._current else Colors.TEXT_SECONDARY)
            painter.setPen(QColor(label_color))
            painter.drawText(cx - label_width // 2, label_y, label_width, 20,
                             Qt.AlignmentFlag.AlignCenter, self._steps[i])

        painter.end()

    def stop(self):
        self._pulse_timer.stop()
