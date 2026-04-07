"""主窗口 - 深空美学 · 多浏览器兼容布局"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEasingCurve
from PySide6.QtGui import QFont, QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsOpacityEffect
from .theme import Colors, set_dark, is_dark, apply_theme
from .components import FABButton
from .home_page import HomePage
from .add_page import AddPage
from .log_page import LogPage


class BrowserStatusIndicator(QFrame):
    """
    浏览器状态指示器 — 显示自动检测到的浏览器。
    圆点 + 浏览器名称 + 版本号。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._browser_name = "检测中..."
        self._browser_version = ""
        self._online = False
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detect_browser()

    def _detect_browser(self):
        import threading
        def detect():
            try:
                from ..browser.factory import detect_browser
                browser, version = detect_browser()
                self._browser_name = browser.name
                self._browser_version = version.split(".")[0] if version else ""
                self._online = True
            except Exception:
                self._browser_name = "未检测到"
                self._browser_version = ""
                self._online = False
            self.update()

        t = threading.Thread(target=detect, daemon=True)
        t.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 圆点
        dot_color = QColor(Colors.SUCCESS if self._online else Colors.TEXT_DISABLED)
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, (self.height() - 8) // 2, 8, 8)

        # 文字
        font = QFont("Segoe UI Variable", 11)
        if not font.exactMatch():
            font = QFont("Segoe UI", 11)
        painter.setFont(font)
        color = QColor(Colors.TEXT_SECONDARY if self._online else Colors.TEXT_DISABLED)
        painter.setPen(color)
        label = self._browser_name
        if self._browser_version:
            label += f"  {self._browser_version}"
        if not self._online:
            label = "未检测到浏览器"
        painter.drawText(18, 0, self.width() - 8, self.height(),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         label)
        painter.end()

    def minimumSizeHint(self):
        return QSize(100, 26)


class NavButton(QPushButton):
    """侧边栏导航按钮"""
    def __init__(self, icon: str, text: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._text = text
        self.setText(f"  {icon}  {text}  ")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self._set_style(False)

    def _set_style(self, active: bool):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {Colors.ACCENT}18;
                    color: {Colors.ACCENT};
                    border: none;
                    border-radius: 8px;
                    padding: 0 14px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: 600;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Colors.TEXT_SECONDARY};
                    border: none;
                    border-radius: 8px;
                    padding: 0 14px;
                    text-align: left;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background: {Colors.CARD};
                    color: {Colors.TEXT_PRIMARY};
                }}
            """)

    def set_active(self, active: bool):
        self.setChecked(active)
        self._set_style(active)


class MainWindow(QMainWindow):
    """主窗口"""
    page_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCTR Export")
        self.setMinimumSize(QSize(1100, 700))
        self.resize(1300, 800)

        # 居中显示
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

        self._setup_ui()

        # 时钟
        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        from datetime import datetime
        self._clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 顶部标题栏 ──
        title_bar = QFrame()
        title_bar.setFixedHeight(56)
        _tb_ss = f"""
            QFrame {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """
        title_bar.setStyleSheet(_tb_ss)
        title_bar._ss = _tb_ss
        self._title_bar = title_bar
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(20, 0, 20, 0)

        # 浏览器状态指示器（左侧）
        self._browser_status = BrowserStatusIndicator()
        self._browser_status.setToolTip("自动检测到的浏览器内核")
        self._browser_status.setStyleSheet(f"""
            QFrame {{
                background: {Colors.CARD}44;
                border: 1px solid {Colors.BORDER};
                border-radius: 13px;
                padding: 0 10px 0 4px;
            }}
            QFrame:hover {{
                background: {Colors.CARD_HOVER}44;
            }}
        """)
        tb_layout.addWidget(self._browser_status)

        tb_layout.addSpacing(12)

        # 主题切换按钮
        self._theme_btn = QPushButton()
        self._update_theme_btn_style()
        self._theme_btn.setFixedHeight(32)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.clicked.connect(self._toggle_theme)
        tb_layout.addWidget(self._theme_btn)

        tb_layout.addStretch()

        # 标题
        title = QLabel("CCTR Export")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {Colors.TEXT_PRIMARY};")
        tb_layout.addWidget(title)

        tb_layout.addStretch()

        # 平台标签
        platform_badge = QFrame()
        platform_badge.setFixedHeight(26)
        platform_badge.setStyleSheet(f"""
            QFrame {{
                background: {Colors.ACCENT_LIGHT};
                color: {Colors.ACCENT};
                border-radius: 13px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        pb_layout = QHBoxLayout(platform_badge)
        pb_layout.setContentsMargins(0, 0, 0, 0)
        pb_layout.setSpacing(0)
        lbl = QLabel("多平台 · 多浏览器")
        lbl.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: 600;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pb_layout.addWidget(lbl)
        tb_layout.addWidget(platform_badge)

        tb_layout.addSpacing(16)

        self._clock_label = QLabel()
        self._clock_label.setStyleSheet(f"font-size: 12px; color: {Colors.TEXT_SECONDARY};")
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tb_layout.addWidget(self._clock_label)
        main_layout.addWidget(title_bar)

        # ── 下方：侧栏 + 内容 ──
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 左侧导航栏（窄）
        sidebar = QFrame()
        sidebar.setFixedWidth(160)
        _sb_ss = f"""
            QFrame {{
                background: {Colors.SIDEBAR};
                border-right: 1px solid {Colors.BORDER};
            }}
        """
        sidebar.setStyleSheet(_sb_ss)
        sidebar._ss = _sb_ss
        self._sidebar = sidebar
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 16, 10, 16)
        sb_layout.setSpacing(4)

        self._nav_buttons: list[tuple[NavButton, str, QWidget]] = []
        nav_items = [
            ("📋", "主页", "home"),
            ("➕", "添加任务", "add"),
            ("📝", "运行日志", "log"),
        ]

        for icon, text, page_id in nav_items:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked, pid=page_id: self._switch_page(pid))
            sb_layout.addWidget(btn)
            page_widget = self._create_page(page_id)
            self._nav_buttons.append((btn, page_id, page_widget))
            # 存储初始页引用
            if page_id == "home":
                self._home_page = page_widget
            elif page_id == "add":
                self._add_page = page_widget
            elif page_id == "log":
                self._log_page = page_widget

        sb_layout.addStretch()
        body_layout.addWidget(sidebar)

        # 主内容区
        self._stack = QStackedWidget()
        _stack_ss = f"background: {Colors.BG};"
        self._stack.setStyleSheet(_stack_ss)
        self._stack._ss = _stack_ss
        for _, _, page in self._nav_buttons:
            self._stack.addWidget(page)
        body_layout.addWidget(self._stack, stretch=1)

        # 当前页跟踪
        self._current_page_id = "home"

        main_layout.addWidget(body)

        # FAB
        self._fab = FABButton("＋")
        self._fab.setParent(central)
        self._fab.clicked.connect(lambda: self._switch_page("add"))
        central.installEventFilter(self)

        # 状态栏
        from PySide6.QtWidgets import QStatusBar
        status = QStatusBar()
        self.setStatusBar(status)
        self._status_label = QLabel("就绪")
        status.addPermanentWidget(self._status_label)

        # 默认页
        self._switch_page("home")

    def _create_page(self, page_id: str) -> QWidget:
        if page_id == "home":
            return HomePage()
        elif page_id == "add":
            page = AddPage()
            page.task_created.connect(lambda: self._switch_page("home"))
            return page
        elif page_id == "log":
            return LogPage()
        return QWidget()

    def _switch_page(self, page_id: str):
        # 页切换动画：淡入
        for i, (btn, pid, _) in enumerate(self._nav_buttons):
            btn.set_active(pid == page_id)
            if pid == page_id:
                target_idx = i

        # 淡出当前页（如果正在显示）
        cur_widget = self._stack.currentWidget()
        if cur_widget:
            cur_opacity = QGraphicsOpacityEffect(cur_widget)
            cur_widget.setGraphicsEffect(cur_opacity)

            class FadeOut:
                def __init__(self, w, effect):
                    self.w = w
                    self.effect = effect
                    self.opacity = 1.0
                def tick(self):
                    self.opacity -= 0.15
                    if self.opacity <= 0:
                        self.w.setGraphicsEffect(None)
                        return False
                    self.effect.setOpacity(max(0, self.opacity))
                    self.w.setGraphicsEffect(self.effect)
                    return True

            fo = FadeOut(cur_widget, cur_opacity)

            def step():
                if fo.tick():
                    QTimer.singleShot(16, step)
                else:
                    self._stack.setCurrentIndex(target_idx)
                    # 淡入新页
                    new_widget = self._stack.currentWidget()
                    new_opacity = QGraphicsOpacityEffect(new_widget)
                    new_opacity.setOpacity(0)
                    new_widget.setGraphicsEffect(new_opacity)

                    class FadeIn:
                        def __init__(self, w, effect):
                            self.w = w
                            self.effect = effect
                            self.opacity = 0.0
                        def tick(self):
                            self.opacity += 0.15
                            if self.opacity >= 1.0:
                                self.w.setGraphicsEffect(None)
                                return False
                            self.effect.setOpacity(min(1.0, self.opacity))
                            self.w.setGraphicsEffect(self.effect)
                            return True

                    fi = FadeIn(new_widget, new_opacity)
                    def step_in():
                        if fi.tick():
                            QTimer.singleShot(16, step_in)
                    step_in()

            QTimer.singleShot(16, step)

        self._current_page_id = page_id
        self.page_changed.emit(page_id)
        self._fab.setVisible(page_id == "home")

    def _update_theme_btn_style(self):
        """更新主题按钮样式"""
        dark = is_dark()
        icon = "☀️" if dark else "🌙"
        label = "浅色模式" if dark else "深色模式"
        self._theme_btn.setText(f"  {icon}  {label}  ")
        self._theme_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.CARD};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.BORDER};
                border-radius: 20px;
                font-size: 13px;
                font-weight: 500;
                padding: 0 14px;
                text-align: left;
                min-width: 110px;
            }}
            QPushButton:hover {{
                background: {Colors.CARD_HOVER};
                color: {Colors.TEXT_PRIMARY};
                border-color: {Colors.ACCENT}66;
            }}
        """)

    def _toggle_theme(self):
        """切换深/浅色主题"""
        new_dark = not is_dark()
        set_dark(new_dark)
        apply_theme(QApplication.instance())
        self._update_theme_btn_style()

        # 刷新主窗口结构样式（用新 f-string 实时求值 Colors）
        self._title_bar.setStyleSheet(f"""
            QFrame {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        self._sidebar.setStyleSheet(f"""
            QFrame {{
                background: {Colors.SIDEBAR};
                border-right: 1px solid {Colors.BORDER};
            }}
        """)
        self._browser_status.setStyleSheet(f"""
            QFrame {{
                background: {Colors.CARD}44;
                border: 1px solid {Colors.BORDER};
                border-radius: 13px;
                padding: 0 10px 0 4px;
            }}
        """)
        self._stack.setStyleSheet(f"background: {Colors.BG};")

        # 重建所有页面（确保新 Colors 值被使用）
        self._recreate_pages()

    def _recreate_pages(self):
        """重建所有页面，确保使用当前主题颜色"""
        # 记住当前页
        cur = self._current_page_id

        # 清理旧页面
        for _, _, page in self._nav_buttons:
            self._stack.removeWidget(page)
            page.deleteLater()

        # 重建
        self._home_page = HomePage()
        self._add_page = AddPage()
        self._add_page.task_created.connect(lambda: self._switch_page("home"))
        self._log_page = LogPage()

        new_pages_map = {
            "home": self._home_page,
            "add": self._add_page,
            "log": self._log_page,
        }
        self._stack.addWidget(self._home_page)
        self._stack.addWidget(self._add_page)
        self._stack.addWidget(self._log_page)

        # 重建 nav_buttons（保留按钮引用，更新页面引用）
        for i, (btn, pid, _) in enumerate(self._nav_buttons):
            self._nav_buttons[i] = (btn, pid, new_pages_map[pid])

        # 恢复
        self._switch_page(cur)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fab.move(self.width() - 80, self.height() - 140)

    def showEvent(self, event):
        super().showEvent(event)
        self._fab.move(self.width() - 80, self.height() - 140)

    def eventFilter(self, obj, event):
        if obj == self.centralWidget() and event.type() == event.Type.Resize:
            self._fab.move(self.centralWidget().width() - 80, self.centralWidget().height() - 140)
        return super().eventFilter(obj, event)

    def update_status(self, text: str):
        self._status_label.setText(text)
