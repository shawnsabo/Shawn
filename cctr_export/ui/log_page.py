"""运行日志页面 - Element Plus / 若依 RuoYi 双栏风格"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from ..core.database import get_all_tasks, get_logs, TaskStatus, LogLevel
from .components import Card
from .theme import Colors


class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("运行日志")
        title.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setFixedSize(64, 32)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        # 左侧任务列表
        left_card = Card(padding=10)
        left_card.setFixedWidth(280)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(6, 6, 6, 6)

        task_label = QLabel("任务列表")
        task_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; padding: 4px 6px;")
        left_layout.addWidget(task_label)

        self._task_list = QListWidget()
        _tl_ss = f"""
            QListWidget {{
                background: {Colors.CARD};
                border: 1px solid {Colors.SEPARATOR};
                border-radius: 4px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 12px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px 10px;
                border-radius: 3px;
                margin: 1px 0;
            }}
            QListWidget::item:selected {{
                background: {Colors.ACCENT_LIGHT};
                color: {Colors.ACCENT};
                font-weight: 600;
            }}
            QListWidget::item:hover {{
                background: {Colors.FILL_PRIMARY};
            }}
        """
        self._task_list.setStyleSheet(_tl_ss)
        self._task_list._ss = _tl_ss
        self._task_list.currentRowChanged.connect(self._on_task_changed)
        left_layout.addWidget(self._task_list)
        left_card.addLayout(left_layout)
        body.addWidget(left_card)

        # 右侧日志文本
        right_card = Card(padding=14)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(8, 8, 8, 8)

        log_header = QHBoxLayout()
        self._log_title = QLabel("选择一个任务查看日志")
        self._log_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        log_header.addWidget(self._log_title)
        log_header.addStretch()
        right_layout.addLayout(log_header)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        _lt_ss = f"""
            QTextEdit, QTextEdit QWidget {{
                background: {Colors.FILL_PRIMARY};
                border: 1px solid {Colors.SEPARATOR};
                border-radius: 4px;
                color: {Colors.TEXT_PRIMARY};
                font-family: 'SF Mono', 'Menlo', 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 10px;
            }}
        """
        self._log_text.setStyleSheet(_lt_ss)
        self._log_text._ss = _lt_ss
        self._log_text.setPlaceholderText("选择左侧任务查看日志...")
        right_layout.addWidget(self._log_text)
        right_card.addLayout(right_layout)
        body.addWidget(right_card, stretch=1)

        layout.addLayout(body)

    def refresh(self):
        tasks = get_all_tasks()
        current = self._task_list.currentRow()
        self._task_list.blockSignals(True)
        self._task_list.clear()
        for t in tasks:
            item = QListWidgetItem(f"#{t.id} - {t.username}")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self._task_list.addItem(item)
        if 0 <= current < self._task_list.count():
            self._task_list.setCurrentRow(current)
        self._task_list.blockSignals(False)
        self._load_logs()

    def refresh_theme(self):
        """切换主题后刷新所有样式"""
        self.setStyleSheet(f"background: {Colors.BG};")
        self._refresh_btn.setStyleSheet(self._refresh_btn._ss)
        self._task_list.setStyleSheet(self._task_list._ss)
        self._log_text.setStyleSheet(self._log_text._ss)
        self._load_logs()

    def _on_task_changed(self, row):
        self._load_logs()

    def _load_logs(self):
        item = self._task_list.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not task_id:
            return

        self._log_title.setText(f"任务 #{task_id} 日志")
        logs = get_logs(task_id)

        level_colors = {
            LogLevel.INFO.value: Colors.ACCENT,
            LogLevel.WARN.value: Colors.WARNING,
            LogLevel.ERROR.value: Colors.ERROR,
        }

        html_lines = []
        for log in logs:
            color = level_colors.get(log["level"], Colors.TEXT_SECONDARY)
            time_str = log["create_time"][:19]
            level = log["level"].upper()
            msg = log["message"]
            html_lines.append(
                f'<span style="color:{Colors.TEXT_DISABLED}">[{time_str}]</span> '
                f'<span style="color:{color};font-weight:600">[{level}]</span> '
                f'<span style="color:{Colors.TEXT_PRIMARY}">{msg}</span>'
            )

        self._log_text.setHtml("<br>".join(html_lines) if html_lines else
                               f'<span style="color:{Colors.TEXT_SECONDARY}">暂无日志</span>')
