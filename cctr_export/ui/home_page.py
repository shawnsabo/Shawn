"""任务列表主页 - 卡片式布局"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt
from ..core.database import (
    get_all_tasks, delete_task, update_task_status,
    TaskStatus, ExportType
)
from ..core.tasks import engine
from .components import Card, SectionTitle, StatusBadge, EmptyState, TaskCard
from .theme import Colors


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 16)
        layout.setSpacing(16)

        # 顶部：标题 + 统计卡片 + 搜索 + 刷新
        header = QVBoxLayout()
        header.setSpacing(12)

        # 第一行：标题 + 刷新
        row1 = QHBoxLayout()
        self._title = SectionTitle("任务列表")
        row1.addWidget(self._title)
        row1.addStretch()

        # 刷新按钮
        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedSize(36, 36)
        self._refresh_btn.setToolTip("刷新列表")
        self._refresh_btn.clicked.connect(self.refresh)
        _btn_ss = f"""
            QPushButton {{
                background: {Colors.CARD};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                font-size: 15px;
                min-height: auto;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {Colors.CARD_HOVER};
                color: {Colors.ACCENT};
                border-color: {Colors.ACCENT}66;
            }}
        """
        self._refresh_btn.setStyleSheet(_btn_ss)
        self._refresh_btn._ss = _btn_ss
        row1.addWidget(self._refresh_btn)
        header.addLayout(row1)

        # 第二行：统计概览 + 搜索
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # 统计数字（通过 refresh 更新）
        self._stat_waiting = QLabel("0")
        self._stat_processing = QLabel("0")
        self._stat_success = QLabel("0")
        self._stat_failed = QLabel("0")

        def make_stat_widget(num_label: QLabel, label_text: str, color: str) -> QFrame:
            f = QFrame()
            f.setStyleSheet(f"""
                QFrame {{
                    background: {Colors.CARD};
                    border: 1px solid {Colors.BORDER};
                    border-radius: 10px;
                    padding: 10px 16px;
                    min-width: 90px;
                }}
            """)
            vl = QVBoxLayout(f)
            vl.setSpacing(2)
            vl.setContentsMargins(12, 10, 12, 10)
            num_label.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 11px; color: {Colors.TEXT_SECONDARY}; font-weight: 500;")
            vl.addWidget(num_label)
            vl.addWidget(lbl)
            return f

        self._stat_waiting_w = make_stat_widget(self._stat_waiting, "等待中", Colors.WARNING)
        self._stat_processing_w = make_stat_widget(self._stat_processing, "进行中", Colors.INFO)
        self._stat_success_w = make_stat_widget(self._stat_success, "已成功", Colors.SUCCESS)
        self._stat_failed_w = make_stat_widget(self._stat_failed, "已失败", Colors.ERROR)

        row2.addWidget(self._stat_waiting_w)
        row2.addWidget(self._stat_processing_w)
        row2.addWidget(self._stat_success_w)
        row2.addWidget(self._stat_failed_w)

        # 搜索框（右侧）
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索任务 ID / 账号...")
        self._search_input.setFixedWidth(220)
        self._search_input.textChanged.connect(self.refresh)
        row2.addStretch()
        row2.addWidget(self._search_input)
        header.addLayout(row2)

        layout.addLayout(header)

        # 滚动区域放卡片
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        _scroll_ss = f"""
            QScrollArea {{
                background: {Colors.BG};
                border: none;
            }}
        """
        self._scroll.setStyleSheet(_scroll_ss)
        self._scroll._ss = _scroll_ss
        self._card_container = QWidget()
        _cc_ss = f"background: {Colors.BG};"
        self._card_container.setStyleSheet(_cc_ss)
        self._card_container._ss = _cc_ss
        self._cards_layout = QVBoxLayout(self._card_container)
        self._cards_layout.setSpacing(12)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._card_container)
        layout.addWidget(self._scroll)

        # 空状态
        self._empty = EmptyState("📭", "还没有任务，点击右下角按钮开始添加")
        _empty_ss = f"background: {Colors.BG};"
        self._empty.setStyleSheet(_empty_ss)
        self._empty._ss = _empty_ss
        layout.addWidget(self._empty)

    def refresh(self):
        all_tasks = get_all_tasks()
        keyword = self._search_input.text().strip().lower()
        if keyword:
            tasks = [t for t in all_tasks if keyword in t.username.lower() or keyword in str(t.id)]
        else:
            tasks = all_tasks

        # 更新统计
        from ..core.database import TaskStatus
        self._stat_waiting.setText(str(sum(1 for t in all_tasks if t.status == TaskStatus.WAITING)))
        self._stat_processing.setText(str(sum(1 for t in all_tasks if t.status == TaskStatus.PROCESSING)))
        self._stat_success.setText(str(sum(1 for t in all_tasks if t.status == TaskStatus.SUCCESS)))
        self._stat_failed.setText(str(sum(1 for t in all_tasks if t.status == TaskStatus.FAILED)))

        # 清空旧卡片
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self._empty.setVisible(len(tasks) == 0)
        self._scroll.setVisible(len(tasks) > 0)

        for t in tasks:
            card = self._create_task_card(t)
            self._cards_layout.addWidget(card)

    def refresh_theme(self):
        """切换主题后刷新所有样式"""
        self.setStyleSheet(f"background: {Colors.BG};")
        self._refresh_btn.setStyleSheet(self._refresh_btn._ss)
        self._scroll.setStyleSheet(self._scroll._ss)
        self._card_container.setStyleSheet(self._card_container._ss)
        self._empty.setStyleSheet(self._empty._ss)
        # 重建卡片（卡片样式也依赖 Colors）
        self.refresh()

    def _create_task_card(self, t) -> TaskCard:
        card = TaskCard()

        # 第一行：任务ID + 状态
        row1 = QHBoxLayout()
        id_label = QLabel(f"任务 #{t.id}")
        id_label.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        row1.addWidget(id_label)
        row1.addStretch()
        badge = StatusBadge(t.status.value)
        row1.addWidget(badge)
        card.addLayout(row1)

        # 第二行：账号 + 格式 + 时间
        row2 = QHBoxLayout()
        account = QLabel(f"👤 {t.username}")
        account.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY};")
        row2.addWidget(account)

        fmt_text = "PDF" if t.export_type == ExportType.PDF else "PNG"
        fmt_label = QLabel(f"📄 {fmt_text}")
        fmt_label.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY};")
        row2.addWidget(fmt_label)

        time_label = QLabel(f"🕐 {t.create_time[:19]}")
        time_label.setStyleSheet(f"font-size: 12px; color: {Colors.TEXT_SECONDARY};")
        row2.addStretch()
        row2.addWidget(time_label)
        card.addLayout(row2)

        # 第三行：操作按钮
        row3 = QHBoxLayout()
        row3.setSpacing(8)

        if t.status == TaskStatus.WAITING:
            run_btn = QPushButton("▶ 运行")
            run_btn.setFixedWidth(80)
            run_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.SUCCESS};
                    color: #fff;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    min-height: auto;
                }}
                QPushButton:hover {{ background: #4ade80; }}
            """)
            run_btn.clicked.connect(lambda checked, tid=t.id: self._run_task(tid))
            row3.addWidget(run_btn)

        if t.status == TaskStatus.SUCCESS:
            open_btn = QPushButton("📂 打开位置")
            open_btn.setFixedWidth(100)
            open_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.SUCCESS};
                    color: #fff;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    min-height: auto;
                }}
                QPushButton:hover {{ background: #4ade80; }}
            """)
            open_btn.clicked.connect(lambda checked, tid=t.id: self._open_output(tid))
            row3.addWidget(open_btn)

        if t.status == TaskStatus.FAILED:
            retry_btn = QPushButton("🔄 重试")
            retry_btn.setFixedWidth(80)
            retry_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.WARNING};
                    color: #000;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    min-height: auto;
                }}
                QPushButton:hover {{ background: #e5ad2a; }}
            """)
            retry_btn.clicked.connect(lambda checked, tid=t.id: self._retry_task(tid))
            row3.addWidget(retry_btn)

        del_btn = QPushButton("🗑 删除")
        del_btn.setFixedWidth(80)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.ERROR};
                border: 1px solid {Colors.ERROR}44;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                min-height: auto;
            }}
            QPushButton:hover {{
                background: {Colors.ERROR}22;
            }}
        """)
        del_btn.clicked.connect(lambda checked, tid=t.id: self._delete_task(tid))
        row3.addWidget(del_btn)
        row3.addStretch()
        card.addLayout(row3)

        return card

    def _run_task(self, task_id: int):
        engine.run_task(task_id)
        self.refresh()

    def _retry_task(self, task_id: int):
        update_task_status(task_id, TaskStatus.WAITING)
        engine.run_task(task_id)
        self.refresh()

    def _delete_task(self, task_id: int):
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除此任务吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_task(task_id)
            self.refresh()

    def _open_output(self, task_id: int):
        """打开任务导出结果所在文件夹"""
        import os, subprocess
        zip_path = os.path.join(os.path.expanduser("~"), ".cctr_export", "output", f"task_{task_id}.zip")
        folder = os.path.dirname(zip_path)
        if os.path.exists(folder):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(zip_path)])
        else:
            QMessageBox.information(self, "提示", f"导出文件夹不存在：\n{folder}")
