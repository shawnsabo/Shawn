"""UI 组件库 — Element Plus 组件规范（若依 RuoYi 视觉）

el-card / el-tag / el-steps / el-button 语义的 Qt 实现。
所有类名与对外 API 与原版一致。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QProgressBar, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from .theme import Colors


class Card(QFrame):
    """el-card：白底 + 1px #EBEEF5 描边 + 轻阴影"""
    def __init__(self, parent=None, radius: int = 4, padding: int = 20, shadow: bool = True):
        super().__init__(parent)
        self._radius = radius
        self.setObjectName("Card")
        self.setStyleSheet(f"""
            #Card {{
                background: {Colors.CARD};
                border: 1px solid {Colors.SEPARATOR};
                border-radius: {radius}px;
            }}
        """)
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(12)
            effect.setColor(QColor(Colors.SHADOW))
            effect.setOffset(0, 2)
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
    """el-tag：语义色 light 底 + 同色文字 + 描边，4px 圆角"""
    STYLES = {
        "waiting": ("等待", Colors.WARNING),
        "processing": ("进行中", Colors.ACCENT),
        "success": ("成功", Colors.SUCCESS),
        "failed": ("失败", Colors.ERROR),
    }

    def __init__(self, status: str, parent=None):
        text, color = self.STYLES.get(status, (status, Colors.INFO))
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            background: {color}1A;
            color: {color};
            border: 1px solid {color}4D;
            padding: 1px 9px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        """)
        self.setFixedHeight(24)


class SkeletonLoader(QFrame):
    """骨架屏加载器（fill 灰块脉冲）"""
    def __init__(self, width=200, height=16, radius=4, parent=None):
        super().__init__(parent)
        self._w = width
        self._h = height
        self._radius = radius
        self.setFixedSize(width, height)
        self._opacity = 0.4
        self._dir = 1
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(30)

    def _pulse(self):
        self._opacity += 0.015 * self._dir
        if self._opacity >= 0.75:
            self._dir = -1
        elif self._opacity <= 0.35:
            self._dir = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(Colors.TEXT_SECONDARY)
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)
        painter.end()

    def stop(self):
        self._timer.stop()


class SkeletonCard(QWidget):
    """骨架屏任务卡片 — 3行骨架模拟真实卡片布局"""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 16, 20, 16)
        self.setFixedHeight(110)

        row1 = QHBoxLayout()
        row1.addWidget(SkeletonLoader(80, 22, 4))
        row1.addStretch()
        row1.addWidget(SkeletonLoader(70, 22, 4))
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(SkeletonLoader(120, 13, 4))
        row2.addSpacing(16)
        row2.addWidget(SkeletonLoader(50, 13, 4))
        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(SkeletonLoader(70, 28, 4))
        row3.addSpacing(8)
        row3.addWidget(SkeletonLoader(70, 28, 4))
        row3.addStretch()
        layout.addLayout(row3)


class SpinningIndicator(QWidget):
    """加载动画（primary 弧线）"""
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
    """页面标题（14px 600，el-page-header 风格）"""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            font-size: 18px;
            font-weight: 600;
            color: {Colors.TEXT_PRIMARY};
            padding: 2px 0;
        """)


class EmptyState(QWidget):
    """空状态提示"""
    def __init__(self, icon: str = "", text: str = "暂无数据", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        if icon:
            lbl_icon = QLabel(icon)
            lbl_icon.setStyleSheet("font-size: 44px;")
            lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl_icon)
        lbl_text = QLabel(text)
        lbl_text.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_text)


class FABButton(QPushButton):
    """圆形主操作按钮（primary solid）"""
    def __init__(self, icon: str = "＋", parent=None):
        super().__init__(icon, parent)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(hover=False)

    def _apply_style(self, hover: bool):
        c = Colors
        bg = c.ACCENT_HOVER if hover else c.ACCENT
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: #ffffff;
                border: none;
                border-radius: 28px;
                font-size: 24px;
                font-weight: 600;
            }}
        """)

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)


class TaskCard(QFrame):
    """任务卡片（el-card：描边卡片，hover 阴影抬升）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TaskCard")
        self.setStyleSheet(f"""
            #TaskCard {{
                background: {Colors.CARD};
                border: 1px solid {Colors.SEPARATOR};
                border-radius: 4px;
            }}
        """)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setColor(QColor("#00000000"))
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)

    def enterEvent(self, event):
        self._shadow.setBlurRadius(16)
        self._shadow.setColor(QColor(Colors.SHADOW))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setBlurRadius(8)
        self._shadow.setColor(QColor("#00000000"))
        super().leaveEvent(event)

    def addWidget(self, w):
        self._layout.addWidget(w)

    def addLayout(self, l):
        self._layout.addLayout(l)

    def layout(self):
        return self._layout


class StepIndicator(QWidget):
    """el-steps：done=primary 实底✓ / current=白底 primary 描边 / waiting=#C0C4CC"""
    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self._steps = steps
        self._current = 0
        self.setFixedHeight(72)
        self._step_colors = {
            "done": Colors.ACCENT,
            "active": Colors.ACCENT,
            "pending": Colors.TEXT_DISABLED,
        }

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

        label_y_center = h // 2 + 6
        circle_y_center = h // 2 - 16
        label_y = circle_y_center + 26

        label_width = max(100, w // n - 20)
        total_content_w = n * label_width + (n - 1) * 20
        start_x = (w - total_content_w) // 2

        for i in range(n):
            cx = start_x + i * (label_width + 20) + label_width // 2

            if i > 0:
                prev_cx = start_x + (i - 1) * (label_width + 20) + label_width // 2
                line_color = self._step_colors["done"] if i <= self._current else self._step_colors["pending"]
                painter.setPen(QPen(QColor(line_color), 2))
                painter.drawLine(prev_cx + 12, circle_y_center, cx - 12, circle_y_center)

            r = 11
            if i < self._current:
                painter.setBrush(QColor(self._step_colors["done"]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(cx - r, circle_y_center - r, r * 2, r * 2)
                font = painter.font()
                font.setPixelSize(12)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff"))
                painter.drawText(cx - r, circle_y_center - r, r * 2, r * 2,
                                 Qt.AlignmentFlag.AlignCenter, "✓")
            elif i == self._current:
                # el-steps process：白底 + 2px primary 描边 + primary 数字
                painter.setBrush(QColor(Colors.CARD))
                pen = QPen(QColor(self._step_colors["active"]), 2)
                painter.setPen(pen)
                painter.drawEllipse(cx - r, circle_y_center - r, r * 2, r * 2)
                font = painter.font()
                font.setPixelSize(12)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(self._step_colors["active"]))
                painter.drawText(cx - r, circle_y_center - r, r * 2, r * 2,
                                 Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(QColor(self._step_colors["pending"]), 1.5)
                painter.setPen(pen)
                painter.drawEllipse(cx - r, circle_y_center - r, r * 2, r * 2)
                font = painter.font()
                font.setPixelSize(11)
                painter.setFont(font)
                painter.setPen(QColor(self._step_colors["pending"]))
                painter.drawText(cx - r, circle_y_center - r, r * 2, r * 2,
                                 Qt.AlignmentFlag.AlignCenter, str(i + 1))

            font = painter.font()
            font.setPixelSize(12)
            font.setBold(i == self._current)
            painter.setFont(font)
            if i == self._current:
                label_color = Colors.TEXT_PRIMARY
            elif i < self._current:
                label_color = self._step_colors["done"]
            else:
                label_color = Colors.TEXT_SECONDARY
            painter.setPen(QColor(label_color))
            painter.drawText(cx - label_width // 2, label_y, label_width, 18,
                             Qt.AlignmentFlag.AlignCenter, self._steps[i])

        painter.end()

    def stop(self):
        pass
