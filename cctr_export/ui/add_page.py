"""添加任务页面 - 步骤向导式 UI"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QScrollArea,
    QGridLayout, QSizePolicy, QMessageBox, QFrame, QStackedWidget,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from ..core.api import CCTRClient
from ..core.database import add_task, ExportType
from ..core.tasks import engine
from ..core.models import Practice, ChapterType, QuestionType
from .components import Card, StepIndicator
from .theme import Colors


class AddPage(QWidget):
    task_created = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client: CCTRClient | None = None
        self._practices: list[Practice] = []
        self._chapters: list[ChapterType] = []
        self._qtypes: list[QuestionType] = []
        self._selected_practice: Practice | None = None
        self._selected_practices: list[Practice] = []
        self._current_step = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {Colors.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 16, 32, 16)
        layout.setSpacing(12)

        # 返回主页按钮
        back_home_row = QHBoxLayout()
        self._back_home_btn = QPushButton("← 返回主页")
        self._back_home_btn.setFlat(True)
        self._back_home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_home_btn.clicked.connect(lambda: self._go_home())
        _bh_ss = f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: none;
                font-size: 13px;
                padding: 4px 0;
            }}
            QPushButton:hover {{
                color: {Colors.ACCENT};
            }}
        """
        self._back_home_btn.setStyleSheet(_bh_ss)
        self._back_home_btn._ss = _bh_ss
        back_home_row.addWidget(self._back_home_btn)
        back_home_row.addStretch()
        layout.addLayout(back_home_row)

        # 步骤指示器卡片（带阴影）
        step_card = QFrame()
        step_card.setStyleSheet(f"""
            QFrame {{
                background: {Colors.CARD};
                border: 1px solid {Colors.BORDER};
                border-radius: 16px;
            }}
        """)
        effect = QGraphicsDropShadowEffect(step_card)
        effect.setBlurRadius(20)
        effect.setColor(QColor(Colors.SHADOW + "30"))
        effect.setOffset(0, 4)
        step_card.setGraphicsEffect(effect)
        step_card_layout = QVBoxLayout(step_card)
        step_card_layout.setContentsMargins(24, 20, 24, 20)
        self._step_indicator = StepIndicator(["登录", "选择练习", "导出设置"])
        step_card_layout.addWidget(self._step_indicator)
        layout.addWidget(step_card)

        # 步骤内容区
        self._step_stack = QStackedWidget()
        _stack_ss = f"background: {Colors.CARD}; border-radius: 16px; border: 1px solid {Colors.BORDER};"
        self._step_stack.setStyleSheet(_stack_ss)
        self._step_stack._ss = _stack_ss
        layout.addWidget(self._step_stack, stretch=1)

        # ── Step 1: 登录 ──
        self._step1_widget = QWidget()
        self._step1_widget.setStyleSheet(f"background: {Colors.BG};")
        s1 = QVBoxLayout(self._step1_widget)
        s1.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        login_card = Card(padding=28)
        lc = QVBoxLayout()
        lc.setSpacing(18)

        lc_title = QLabel("登录 CCTRCloud")
        lc_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        lc_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lc.addWidget(lc_title)

        lc_desc = QLabel("输入你的账号信息以连接平台")
        lc_desc.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY};")
        lc_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lc.addWidget(lc_desc)

        # 分隔线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        lc.addWidget(sep)

        # 表单
        form = QGridLayout()
        form.setSpacing(12)

        form.addWidget(self._make_label("学校编号"), 0, 0)
        self._school_input = QLineEdit()
        self._school_input.setPlaceholderText("输入学校编号")
        form.addWidget(self._school_input, 0, 1)

        form.addWidget(self._make_label("用户名"), 1, 0)
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("输入用户名")
        form.addWidget(self._user_input, 1, 1)

        form.addWidget(self._make_label("密码"), 2, 0)
        self._pass_input = QLineEdit()
        self._pass_input.setPlaceholderText("输入密码")
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self._pass_input, 2, 1)

        lc.addLayout(form)

        self._login_status = QLabel("")
        self._login_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lc.addWidget(self._login_status)

        self._login_btn = QPushButton("🔗 登录")
        self._login_btn.setFixedHeight(44)
        self._login_btn.clicked.connect(self._do_login)
        lc.addWidget(self._login_btn)

        login_card.addLayout(lc)
        s1.addWidget(login_card)
        self._step_stack.addWidget(self._step1_widget)

        # ── Step 2: 选择练习 ──
        self._step2_widget = QWidget()
        self._step2_widget.setStyleSheet(f"background: {Colors.BG};")
        self._step2_widget.setVisible(False)
        s2 = QVBoxLayout(self._step2_widget)

        # 顶部操作栏
        s2_header = QHBoxLayout()
        select_all_cb = QCheckBox("全选所有练习")
        select_all_cb.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        select_all_cb.stateChanged.connect(self._on_select_all_practices)
        s2_header.addWidget(select_all_cb)
        s2_header.addStretch()

        self._selected_count_label = QLabel("已选 0 个练习")
        self._selected_count_label.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY};")
        s2_header.addWidget(self._selected_count_label)
        s2.addLayout(s2_header)

        # 练习列表（滚动）
        self._practice_list_widget = QWidget()
        self._practice_list_widget.setStyleSheet(f"background: {Colors.BG};")
        self._practice_list_layout = QVBoxLayout(self._practice_list_widget)
        self._practice_list_layout.setSpacing(6)
        self._practice_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._practice_checks: list[tuple[QCheckBox, Practice]] = []

        practice_scroll = QScrollArea()
        practice_scroll.setWidgetResizable(True)
        practice_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        practice_scroll.setStyleSheet(f"background: {Colors.BG};")
        practice_scroll.setWidget(self._practice_list_widget)
        practice_scroll.setMinimumHeight(300)
        s2.addWidget(practice_scroll)

        # 底部导航
        s2_nav = QHBoxLayout()
        s2_nav.addStretch()
        back_btn = self._make_back_btn()
        back_btn.clicked.connect(lambda: self._go_step(0))
        s2_nav.addWidget(back_btn)
        next_btn = QPushButton("下一步 →")
        next_btn.setFixedWidth(120)
        next_btn.clicked.connect(self._go_step2_to_3)
        s2_nav.addWidget(next_btn)
        s2.addLayout(s2_nav)

        self._step_stack.addWidget(self._step2_widget)

        # ── Step 3: 导出设置 ──
        self._step3_widget = QWidget()
        self._step3_widget.setStyleSheet(f"background: {Colors.BG};")
        self._step3_widget.setVisible(False)
        s3 = QVBoxLayout(self._step3_widget)

        # 说明
        mode_label = QLabel("导出模式说明")
        mode_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        s3.addWidget(mode_label)

        if isinstance(self._selected_practices, list):
            pass  # will be updated

        self._export_mode_label = QLabel("当前为：单练习模式")
        self._export_mode_label.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY};")
        s3.addWidget(self._export_mode_label)

        # 章节筛选
        ch_card = Card(padding=20)
        ch_layout = QVBoxLayout()
        ch_title = QHBoxLayout()
        ch_t = QLabel("📂 章节（留空则全部）")
        ch_t.setStyleSheet(f"font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        ch_title.addWidget(ch_t)
        ch_title.addStretch()
        self._chapter_select_all = QPushButton("全选")
        self._chapter_select_all.setFlat(True)
        self._chapter_select_all.clicked.connect(lambda: self._toggle_all(self._chapter_checks_list, self._chapter_select_all))
        ch_title.addWidget(self._chapter_select_all)
        ch_layout.addLayout(ch_title)

        self._chapter_checks_list: list[QCheckBox] = []
        self._chapter_vlayout = QVBoxLayout()
        self._chapter_vlayout.setSpacing(6)
        ch_layout.addLayout(self._chapter_vlayout)
        ch_card.addLayout(ch_layout)
        s3.addWidget(ch_card)

        # 题型筛选
        qt_card = Card(padding=20)
        qt_layout = QVBoxLayout()
        qt_title = QHBoxLayout()
        qt_t = QLabel("📝 题型（留空则全部）")
        qt_t.setStyleSheet(f"font-weight: 600; color: {Colors.TEXT_PRIMARY};")
        qt_title.addWidget(qt_t)
        qt_title.addStretch()
        self._qtype_select_all = QPushButton("全选")
        self._qtype_select_all.setFlat(True)
        self._qtype_select_all.clicked.connect(lambda: self._toggle_all(self._qtype_checks_list, self._qtype_select_all))
        qt_title.addWidget(self._qtype_select_all)
        qt_layout.addLayout(qt_title)

        self._qtype_checks_list: list[QCheckBox] = []
        self._qtype_vlayout = QVBoxLayout()
        self._qtype_vlayout.setSpacing(6)
        qt_layout.addLayout(self._qtype_vlayout)
        qt_card.addLayout(qt_layout)
        s3.addWidget(qt_card)

        # 已练习筛选
        practiced_row = QHBoxLayout()
        self._practiced_check = QCheckBox("仅导出已练习的题目")
        self._practiced_check.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        practiced_row.addWidget(self._practiced_check)
        practiced_row.addStretch()
        s3.addLayout(practiced_row)

        # 导出格式
        fmt_card = Card(padding=20)
        fmt_layout = QVBoxLayout()
        fmt_t = QLabel("📤 导出格式")
        fmt_t.setStyleSheet(f"font-weight: 600; color: {Colors.TEXT_PRIMARY}; margin-bottom: 8px;")
        fmt_layout.addWidget(fmt_t)
        fmt_btn_row = QHBoxLayout()
        self._fmt_pdf_btn = QPushButton("📄 PDF 文档")
        self._fmt_pdf_btn.setCheckable(True)
        self._fmt_pdf_btn.setChecked(True)
        self._fmt_pdf_btn.clicked.connect(lambda: self._select_format(ExportType.PDF))
        self._fmt_pdf_btn.setFixedHeight(48)
        _pdf_checked = f"""
            QPushButton {{
                background: {Colors.ACCENT};
                color: #fff;
                border-radius: 10px;
                border: 2px solid {Colors.ACCENT};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT};
                border: 2px solid #fff;
                box-shadow: 0 0 0 3px {Colors.ACCENT_LIGHT};
            }}
            QPushButton:!checked {{
                background: {Colors.CARD};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER};
            }}
            QPushButton:!checked:hover {{
                background: {Colors.CARD_HOVER};
                border-color: {Colors.ACCENT}66;
            }}
        """
        _pdf_unchecked = f"""
            QPushButton {{
                background: {Colors.CARD};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER};
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT};
                border: 2px solid #fff;
                box-shadow: 0 0 0 3px {Colors.ACCENT_LIGHT};
            }}
            QPushButton:!checked:hover {{
                background: {Colors.CARD_HOVER};
                border-color: {Colors.ACCENT}66;
            }}
        """
        self._fmt_pdf_btn.setStyleSheet(_pdf_checked)
        self._fmt_pdf_btn._ss_checked = _pdf_checked
        self._fmt_pdf_btn._ss_unchecked = _pdf_unchecked
        fmt_btn_row.addWidget(self._fmt_pdf_btn)

        self._fmt_png_btn = QPushButton("🖼️ PNG 图片")
        self._fmt_png_btn.setCheckable(True)
        self._fmt_png_btn.clicked.connect(lambda: self._select_format(ExportType.IMG))
        self._fmt_png_btn.setFixedHeight(48)
        _png_checked = f"""
            QPushButton {{
                background: {Colors.ACCENT};
                color: #fff;
                border-radius: 10px;
                border: 2px solid {Colors.ACCENT};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT};
                border: 2px solid #fff;
                box-shadow: 0 0 0 3px {Colors.ACCENT_LIGHT};
            }}
            QPushButton:!checked {{
                background: {Colors.CARD};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER};
            }}
            QPushButton:!checked:hover {{
                background: {Colors.CARD_HOVER};
                border-color: {Colors.ACCENT}66;
            }}
        """
        _png_unchecked = f"""
            QPushButton {{
                background: {Colors.CARD};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER};
                border-radius: 10px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:checked {{
                background: {Colors.ACCENT};
                color: #fff;
                border: 2px solid {Colors.ACCENT};
                box-shadow: 0 0 0 3px {Colors.ACCENT_LIGHT};
            }}
            QPushButton:!checked:hover {{
                background: {Colors.CARD_HOVER};
                border-color: {Colors.ACCENT}66;
            }}
        """
        self._fmt_png_btn.setStyleSheet(_png_unchecked)
        self._fmt_png_btn._ss_checked = _png_checked
        self._fmt_png_btn._ss_unchecked = _png_unchecked
        fmt_btn_row.addWidget(self._fmt_png_btn)
        fmt_btn_row.addWidget(self._fmt_png_btn)
        fmt_layout.addLayout(fmt_btn_row)
        fmt_card.addLayout(fmt_layout)
        s3.addWidget(fmt_card)

        # 底部导航
        s3_nav = QHBoxLayout()
        s3_nav.addStretch()
        s3_back = self._make_back_btn()
        s3_back.clicked.connect(lambda: self._go_step(1))
        s3_nav.addWidget(s3_back)

        self._submit_btn = QPushButton("🚀 开始导出")
        self._submit_btn.setFixedSize(160, 48)
        self._submit_btn.clicked.connect(self._submit)
        _sub_ss = f"""
            QPushButton {{
                background: {Colors.SUCCESS};
                color: #fff;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 700;
                min-height: auto;
                padding: 0;
            }}
            QPushButton:hover {{ background: #4ade80; }}
        """
        self._submit_btn.setStyleSheet(_sub_ss)
        self._submit_btn._ss = _sub_ss
        s3_nav.addWidget(self._submit_btn)
        s3.addLayout(s3_nav)

        self._step_stack.addWidget(self._step3_widget)

        # 保存选中的格式
        self._selected_format = ExportType.PDF

    def refresh_theme(self):
        """切换主题后刷新所有样式"""
        self.setStyleSheet(f"background: {Colors.BG};")
        self._back_home_btn.setStyleSheet(self._back_home_btn._ss)
        self._step_stack.setStyleSheet(self._step_stack._ss)
        self._step1_widget.setStyleSheet(self._step1_widget._ss)
        self._step2_widget.setStyleSheet(self._step2_widget._ss)
        self._step3_widget.setStyleSheet(self._step3_widget._ss)
        self._practice_list_widget.setStyleSheet(self._practice_list_widget._ss)
        self._practice_scroll.setStyleSheet(self._practice_scroll._ss)
        # 刷新 step indicator（触发 paintEvent 重绘）
        self._step_indicator.update()
        # 重刷格式按钮
        self._select_format(self._selected_format)
        self._submit_btn.setStyleSheet(self._submit_btn._ss)
        self._login_status.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 13px; color: {Colors.TEXT_SECONDARY}; font-weight: 500;")
        return lbl

    def _make_back_btn(self) -> QPushButton:
        btn = QPushButton("← 返回")
        btn.setFixedWidth(100)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                font-size: 13px;
                min-height: auto;
                padding: 8px 12px;
            }}
            QPushButton:hover {{
                background: {Colors.CARD};
                color: {Colors.TEXT_PRIMARY};
            }}
        """)
        return btn

    def _select_format(self, fmt):
        self._selected_format = fmt
        self._fmt_pdf_btn.setStyleSheet(self._fmt_pdf_btn._ss_checked if fmt == ExportType.PDF else self._fmt_pdf_btn._ss_unchecked)
        self._fmt_pdf_btn.setChecked(fmt == ExportType.PDF)
        self._fmt_png_btn.setStyleSheet(self._fmt_png_btn._ss_checked if fmt == ExportType.IMG else self._fmt_png_btn._ss_unchecked)
        self._fmt_png_btn.setChecked(fmt == ExportType.IMG)

    def _go_home(self):
        """返回主页"""
        self.task_created.emit()

    def _go_step(self, step: int):
        """切换步骤（step: 0/1/2）"""
        self._current_step = step
        self._step_indicator.set_step(step)
        self._step_stack.setCurrentIndex(step)

    def _do_login(self):
        school = self._school_input.text().strip()
        user = self._user_input.text().strip()
        pwd = self._pass_input.text().strip()
        if not school or not user or not pwd:
            self._login_status.setText("❌ 请填写所有字段")
            self._login_status.setStyleSheet(f"color: {Colors.ERROR}; font-size: 13px;")
            return

        self._login_status.setText("正在登录...")
        self._login_status.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 13px;")
        self._login_btn.setEnabled(False)

        from PySide6.QtCore import QThread, Signal

        class LoginThread(QThread):
            result = Signal(object, object, object)
            def __init__(self, school, user, pwd):
                super().__init__()
                self.school = school
                self.user = user
                self.pwd = pwd
            def run(self):
                try:
                    c = CCTRClient(self.school, self.user, self.pwd)
                    c.login()
                    practices = c.get_practice_list()
                    self.result.emit(c, practices, None)
                except Exception as e:
                    self.result.emit(None, None, str(e))

        self._login_thread = LoginThread(school, user, pwd)
        self._login_thread.result.connect(self._on_login_done)
        self._login_thread.start()

    def _on_login_done(self, client, practices, error):
        self._login_btn.setEnabled(True)
        if error:
            self._login_status.setText(f"❌ {error}")
            self._login_status.setStyleSheet(f"color: {Colors.ERROR}; font-size: 13px;")
            return

        self._client = client
        self._practices = practices
        self._login_status.setText(f"✅ 登录成功，获取到 {len(practices)} 个练习")
        self._login_status.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 13px;")

        # 构建练习列表（去重）
        seen = set()
        sorted_practices = sorted(practices, key=lambda p: (p.lesson_name, p.practice_name))
        unique = []
        for p in sorted_practices:
            key = f"{p.lesson_name}|{p.practice_name}"
            if key not in seen:
                seen.add(key)
                unique.append(p)

        # 清空旧列表
        for cb, _ in self._practice_checks:
            cb.setParent(None)
            cb.deleteLater()
        self._practice_checks.clear()

        self._selected_practices = []
        current_lesson = None
        for p in unique:
            # 课程分组标签
            if current_lesson != p.lesson_name:
                if current_lesson is not None:
                    sep = QLabel("")  # 小间距
                    sep.setFixedHeight(8)
                    self._practice_list_layout.addWidget(sep)
                lesson_label = QLabel(f"📚 {p.lesson_name}")
                lesson_label.setStyleSheet(f"""
                    font-size: 12px; font-weight: 700;
                    color: {Colors.TEXT_SECONDARY};
                    padding: 4px 0;
                """)
                self._practice_list_layout.addWidget(lesson_label)
                current_lesson = p.lesson_name

            cb = QCheckBox(p.practice_name)
            cb.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; padding: 4px 0;")
            cb.stateChanged.connect(self._update_selected_count)
            self._practice_checks.append((cb, p))
            self._practice_list_layout.addWidget(cb)

        self._update_selected_count()
        self._go_step(1)

    def _on_select_all_practices(self, state):
        checked = state == Qt.CheckState.Checked.value
        for cb, _ in self._practice_checks:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._update_selected_count()

    def _update_selected_count(self):
        count = sum(1 for cb, _ in self._practice_checks if cb.isChecked())
        self._selected_count_label.setText(f"已选 {count} 个练习")
        self._selected_practices = [p for cb, p in self._practice_checks if cb.isChecked()]

    def _go_step2_to_3(self):
        """从 step2 到 step3：加载第一个选中练习的章节/题型"""
        selected = [p for cb, p in self._practice_checks if cb.isChecked()]
        if not selected:
            QMessageBox.warning(self, "提示", "请至少选择一个练习！")
            return

        self._selected_practices = selected
        is_multi = len(selected) > 1

        if is_multi:
            self._export_mode_label.setText(f"批量模式：已选 {len(selected)} 个练习")
        else:
            self._export_mode_label.setText(f"单练习模式：{selected[0].practice_name}")

        # 加载第一个练习的章节和题型作为筛选参考
        if self._client:
            try:
                chapters, qtypes = self._client.get_chapter_and_question_type(selected[0])
            except Exception:
                chapters, qtypes = [], []

            # 清除旧 checkbox
            for w in self._chapter_checks_list + self._qtype_checks_list:
                w.setParent(None)
                w.deleteLater()
            self._chapter_checks_list.clear()
            self._qtype_checks_list.clear()

            for ch in chapters:
                cb = QCheckBox(ch.name)
                self._chapter_checks_list.append(cb)
                self._chapter_vlayout.addWidget(cb)

            for qt in qtypes:
                cb = QCheckBox(qt.name)
                self._qtype_checks_list.append(cb)
                self._qtype_vlayout.addWidget(cb)

        self._go_step(2)

    def _submit(self):
        """提交导出任务"""
        if not self._client:
            QMessageBox.warning(self, "错误", "未登录！")
            return

        school = self._school_input.text().strip()
        user = self._user_input.text().strip()
        pwd = self._pass_input.text().strip()
        export_type = self._selected_format

        selected = [p for cb, p in self._practice_checks if cb.isChecked()]
        if not selected:
            QMessageBox.warning(self, "提示", "请至少选择一个练习！")
            return

        selected_chapters = [ch for ch, cb in zip(self._chapters, self._chapter_checks_list) if cb.isChecked()]
        selected_qtypes = [qt for qt, cb in zip(self._qtypes, self._qtype_checks_list) if cb.isChecked()]

        try:
            config = []
            for p in selected:
                config.append({
                    "practice": p.to_json(),
                    "chapters": [c.to_dict() for c in selected_chapters],
                    "question_types": [q.to_dict() for q in selected_qtypes],
                })

            task_id = add_task(school, user, pwd, export_type, config)
            engine.run_task(task_id)
            self.task_created.emit()

            QMessageBox.information(self, "成功", f"任务 #{task_id} 已创建并开始运行！\n共 {len(selected)} 个练习。")
            self._reset()
        except Exception as e:
            QMessageBox.critical(self, "失败", f"创建任务失败：{e}")

    def _toggle_all(self, checks: list, btn: QPushButton):
        all_checked = all(cb.isChecked() for cb in checks)
        for cb in checks:
            cb.setChecked(not all_checked)
        btn.setText("取消全选" if not all_checked else "全选")

    def _reset(self):
        if self._client:
            self._client.close()
            self._client = None
        self._school_input.clear()
        self._user_input.clear()
        self._pass_input.clear()
        self._login_status.setText("")
        self._practices = []
        self._selected_practices = []
        for cb, _ in self._practice_checks:
            cb.setChecked(False)
        self._go_step(0)
