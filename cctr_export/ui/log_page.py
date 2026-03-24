"""运行日志页面 - 左侧任务列表 + 右侧日志"""
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
        # 自动刷新
        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(16)

        # 标题
        header = QHBoxLayout()
        title = QLabel("📝 运行日志")
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton("🔄")
        self._refresh_btn.setFixedSize(40, 40)
        _rf_ss = f"""
            QPushButton {{
                background: {Colors.CARD};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-size: 16px;
                min-height: auto;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {Colors.CARD_HOVER};
                color: {Colors.TEXT_PRIMARY};
            }}
        """
        self._refresh_btn.setStyleSheet(_rf_ss)
        self._refresh_btn._ss = _rf_ss
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        # 主体：左侧任务列表 + 右侧日志
        body = QHBoxLayout()
        body.setSpacing(12)

        # 左侧任务列表
        left_card = Card(padding=12)
        left_card.setFixedWidth(280)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(4, 4, 4, 4)

        task_label = QLabel("任务列表")
        task_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_SECONDARY}; padding: 4px 8px;")
        left_layout.addWidget(task_label)

        self._task_list = QListWidget()
        _tl_ss = f"""
            QListWidget {{
                background: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                color: {Colors.TEXT_PRIMARY};
                font-size: 12px;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 6px;
                margin: 2px 0;
            }}
            QListWidget::item:selected {{
                background: {Colors.ACCENT_LIGHT};
                color: {Colors.ACCENT};
            }}
            QListWidget::item:hover {{
                background: {Colors.CARD_HOVER};
            }}
        """
        self._task_list.setStyleSheet(_tl_ss)
        self._task_list._ss = _tl_ss
        self._task_list.currentRowChanged.connect(self._on_task_changed)
        left_layout.addWidget(self._task_list)
        left_card.addLayout(left_layout)
        body.addWidget(left_card)

        # 右侧日志文本
        right_card = Card(padding=16)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(4, 4, 4, 4)

        log_header = QHBoxLayout()
        self._log_title = QLabel("选择一个任务查看日志")
        self._log_title.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_SECONDARY};")
        log_header.addWidget(self._log_title)
        log_header.addStretch()
        right_layout.addLayout(log_header)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        _lt_ss = f"""
            QTextEdit, QTextEdit QWidget {{
                background: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                color: {Colors.TEXT_PRIMARY};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                padding: 8px;
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

        # 彩色日志
        level_colors = {
            LogLevel.INFO.value: Colors.SUCCESS,
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
                f'<span style="color:{Colors.TEXT_SECONDARY}">[{time_str}]</span> '
                f'<span style="color:{color};font-weight:600">[{level}]</span> '
                f'<span style="color:{Colors.TEXT_PRIMARY}">{msg}</span>'
            )

        self._log_text.setHtml("<br>".join(html_lines) if html_lines else
                               f'<span style="color:{Colors.TEXT_SECONDARY}">暂无日志</span>')
