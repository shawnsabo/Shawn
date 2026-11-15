"""PySide6 主题系统 — Element Plus 设计规范（若依 RuoYi 视觉）

依据：Element Plus 官方 CSS 变量（若依前端使用的组件库）
- 主色 --el-color-primary: #409EFF（hover light-3 #79bbff / dark-2 #337ecc）
- 语义色：success #67C23A / warning #E6A23C / danger #F56C6C / info #909399
- 文字：primary #303133 / regular #606266 / secondary #909399 / placeholder #A8ABB2
- 边框：#DCDFE6 / #E4E7ED / #EBEEF5 / #F2F6FC；圆角 4px
- 深色：--el-bg-color #141414 / overlay #1d1e1f / fill #303030 / text #E5EAF3
- 布局：若依经典 chrome — 侧栏 #304156（文字 #BFCBD9）+ 白色顶栏 + #F0F2F5 内容区
"""
from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication


# ──────────────────────────────────────────────────────────────────
# Element Plus · 浅色模式（官方 CSS 变量映射）
# ──────────────────────────────────────────────────────────────────

class LightColors:
    BG          = "#F0F2F5"   # app-main 内容区底色
    SURFACE     = "#FFFFFF"   # navbar 顶栏
    CARD        = "#FFFFFF"   # el-card
    CARD_HOVER  = "#F5F7FA"
    BORDER      = "#DCDFE6"   # --el-border-color（输入框/按钮描边）
    SEPARATOR   = "#EBEEF5"   # --el-border-color-lighter（卡片/表格描边）
    TEXT_PRIMARY   = "#303133"   # --el-text-color-primary
    TEXT_SECONDARY = "#909399"   # --el-text-color-secondary
    TEXT_TERTIARY  = "#A8ABB2"   # --el-text-color-placeholder
    TEXT_DISABLED  = "#C0C4CC"   # --el-text-color-disabled
    # Element 语义色
    ACCENT      = "#409EFF"   # --el-color-primary
    ACCENT_HOVER= "#79BBFF"   # primary light-3（solid hover）
    ACCENT_LIGHT= "#ECF5FF"   # primary light-8（选中底）
    SUCCESS     = "#67C23A"
    SUCCESS_HOVER = "#95D475"  # success light-3
    WARNING     = "#E6A23C"
    WARNING_HOVER = "#EEBE77"
    ERROR       = "#F56C6C"
    ERROR_HOVER = "#F89898"
    INFO        = "#909399"
    # 控件填充
    FIELD_BG        = "#FFFFFF"   # el-input 背景
    FIELD_BG_FOCUS  = "#FFFFFF"
    CONTROL_BG          = "#FFFFFF"   # el-button default（plain）
    CONTROL_BG_HOVER    = "#ECF5FF"   # primary light-9 hover 底
    CONTROL_BG_PRESSED  = "#ECF5FF"
    FILL_PRIMARY        = "#F5F7FA"   # el-table 表头底
    SCROLLBAR       = "#C0C4CC"
    SCROLLBAR_HOVER = "#909399"
    # 若依经典侧栏
    SIDEBAR       = "#304156"
    SIDEBAR_HOVER = "#263445"
    SIDEBAR_TEXT  = "#BFCBD9"
    INPUT_BG    = "#FFFFFF"
    PROGRESS_BG = "#EBEEF5"
    SHADOW      = "#0000001A"   # el-card: 0 2px 12px rgba(0,0,0,.1)
    SHADOW_ACCENT = "#409EFF33"
    SEG_SELECTED_BG = "#409EFF"   # el-radio-button checked = primary 实底
    GRADIENT_PRIMARY_START = "#409EFF"
    GRADIENT_PRIMARY_END   = "#337ECC"


# ──────────────────────────────────────────────────────────────────
# Element Plus · 深色模式（官方 dark CSS 变量映射）
# ──────────────────────────────────────────────────────────────────

class DarkColors:
    BG          = "#141414"   # --el-bg-color
    SURFACE     = "#1D1E1F"   # --el-bg-color-overlay
    CARD        = "#1D1E1F"
    CARD_HOVER  = "#262727"
    BORDER      = "#4C4D4F"   # --el-border-color
    SEPARATOR   = "#414243"   # --el-border-color-lighter
    TEXT_PRIMARY   = "#E5EAF3"
    TEXT_SECONDARY = "#A3A6AD"
    TEXT_TERTIARY  = "#8D9095"
    TEXT_DISABLED  = "#6C6E72"
    ACCENT      = "#409EFF"
    ACCENT_HOVER= "#79BBFF"
    ACCENT_LIGHT= "#409EFF26"
    SUCCESS     = "#67C23A"
    SUCCESS_HOVER = "#95D475"
    WARNING     = "#E6A23C"
    WARNING_HOVER = "#EEBE77"
    ERROR       = "#F56C6C"
    ERROR_HOVER = "#F89898"
    INFO        = "#909399"
    FIELD_BG        = "#141414"
    FIELD_BG_FOCUS  = "#141414"
    CONTROL_BG          = "#303030"   # --el-fill-color
    CONTROL_BG_HOVER    = "#409EFF14"
    CONTROL_BG_PRESSED  = "#409EFF1F"
    FILL_PRIMARY        = "#262727"
    SCROLLBAR       = "#4C4D4F"
    SCROLLBAR_HOVER = "#6A6B6D"
    SIDEBAR       = "#1F2D3D"   # 若依子菜单深色
    SIDEBAR_HOVER = "#263445"
    SIDEBAR_TEXT  = "#BFCBD9"
    INPUT_BG    = "#141414"
    PROGRESS_BG = "#414243"
    SHADOW      = "#00000033"
    SHADOW_ACCENT = "#409EFF40"
    SEG_SELECTED_BG = "#409EFF"
    GRADIENT_PRIMARY_START = "#409EFF"
    GRADIENT_PRIMARY_END   = "#337ECC"


# ── 全局状态 ─────────────────────────────────────────────────────
_dark_mode = True


class _ColorsProxy:
    _current = DarkColors

    def __getattr__(self, name):
        return getattr(self._current, name)


Colors = _ColorsProxy()


def is_dark() -> bool:
    return _dark_mode


def set_dark(dark: bool):
    global _dark_mode
    _dark_mode = dark
    Colors._current = DarkColors if dark else LightColors


# ── 字体（Element 默认字族） ─────────────────────────────────────
FONT_FAMILIES = [
    "Helvetica Neue", "PingFang SC", "Hiragino Sans GB",
    "Microsoft YaHei", "微软雅黑", "Segoe UI",
]


def _make_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSize(point_size)
    f.setWeight(weight)
    return f


def apply_theme(app: QApplication):
    c = Colors

    font = _make_font(10)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(c.BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(c.CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c.FILL_PRIMARY))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.CARD))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(c.CONTROL_BG))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c.TEXT_DISABLED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c.TEXT_DISABLED))
    app.setPalette(palette)
    app.setStyleSheet(_stylesheet(c))


def _stylesheet(c) -> str:
    return f"""
    /* ── 滚动条 ── */
    QScrollBar:vertical {{
        border: none; background: transparent; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c.SCROLLBAR}; min-height: 40px;
        border-radius: 3px; margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c.SCROLLBAR_HOVER}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QScrollBar:horizontal {{
        border: none; background: transparent; height: 6px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {c.SCROLLBAR}; min-width: 40px;
        border-radius: 3px; margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c.SCROLLBAR_HOVER}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

    /* ── 输入框（el-input：白底 #DCDFE6 描边，聚焦 primary） ── */
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: {c.FIELD_BG};
        border: 1px solid {c.BORDER};
        border-radius: 4px;
        padding: 5px 11px;
        color: {c.TEXT_PRIMARY};
        selection-background-color: {c.ACCENT};
        min-height: 30px;
        font-size: 13px;
    }}
    QLineEdit:hover, QTextEdit:hover {{ border-color: {c.TEXT_TERTIARY}; }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {c.ACCENT}; }}
    QLineEdit::placeholder, QTextEdit::placeholder {{ color: {c.TEXT_TERTIARY}; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox QAbstractItemView {{
        background: {c.CARD};
        border: 1px solid {c.SEPARATOR};
        border-radius: 4px;
        selection-background-color: {c.ACCENT};
        selection-color: #ffffff;
        padding: 4px;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{ border-radius: 3px; padding: 5px 10px; }}

    /* ── 按钮（el-button default：白底描边，hover 变 primary） ── */
    QPushButton {{
        background: {c.CONTROL_BG};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER};
        border-radius: 4px;
        padding: 6px 15px;
        font-size: 13px;
        font-weight: 500;
        min-height: 30px;
    }}
    QPushButton:hover {{
        color: {c.ACCENT};
        border-color: {c.ACCENT_LIGHT};
        background: {c.ACCENT_LIGHT};
    }}
    QPushButton:pressed {{
        color: #337ECC;
        border-color: #337ECC;
    }}
    QPushButton:disabled {{
        background: {c.CONTROL_BG}; color: {c.TEXT_DISABLED};
        border-color: {c.SEPARATOR};
    }}
    QPushButton[flat="true"] {{
        background: transparent;
        color: {c.ACCENT};
        border: none;
        font-weight: 500;
        padding: 4px 10px;
    }}
    QPushButton[flat="true"]:hover {{ background: {c.ACCENT_LIGHT}; border-radius: 4px; }}

    /* ── 表格 ── */
    QTableView, QTableWidget {{
        background: {c.CARD};
        border: 1px solid {c.SEPARATOR};
        border-radius: 4px;
        gridline-color: {c.SEPARATOR};
        selection-background-color: {c.ACCENT_LIGHT};
        selection-color: {c.ACCENT};
    }}
    QHeaderView::section {{
        background: {c.FILL_PRIMARY};
        color: {c.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {c.SEPARATOR};
        padding: 8px 12px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTableWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {c.SEPARATOR}; font-size: 13px; }}
    QTableWidget::item:hover {{ background: {c.CARD_HOVER}; }}

    /* ── 复选框（el-checkbox：方形圆角 2px） ── */
    QCheckBox {{ spacing: 8px; color: {c.TEXT_PRIMARY}; font-size: 13px; padding: 2px 0; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border-radius: 2px;
        border: 1px solid {c.BORDER};
        background: {c.CONTROL_BG};
    }}
    QCheckBox::indicator:hover {{ border-color: {c.ACCENT}; }}
    QCheckBox::indicator:checked {{
        background: {c.ACCENT};
        border-color: {c.ACCENT};
        image: none;
    }}
    QCheckBox:hover {{ color: {c.TEXT_PRIMARY}; }}

    /* ── 进度条 ── */
    QProgressBar {{
        background: {c.PROGRESS_BG}; border: none;
        border-radius: 3px; min-height: 6px;
        text-align: center; color: transparent; font-size: 10px;
    }}
    QProgressBar::chunk {{ background: {c.ACCENT}; border-radius: 3px; }}

    /* ── 状态栏 ── */
    QStatusBar {{
        background: {c.SURFACE}; color: {c.TEXT_SECONDARY};
        border-top: 1px solid {c.SEPARATOR};
        font-size: 11px; padding: 3px 16px;
    }}

    /* ── Tab ── */
    QTabWidget::pane {{ border: 1px solid {c.SEPARATOR}; border-radius: 4px; background: {c.CARD}; }}
    QTabBar::tab {{
        background: transparent; color: {c.TEXT_PRIMARY};
        padding: 8px 16px; border: none;
        border-bottom: 2px solid transparent; font-weight: 500; font-size: 13px;
    }}
    QTabBar::tab:selected {{ color: {c.ACCENT}; border-bottom: 2px solid {c.ACCENT}; }}
    QTabBar::tab:hover:!selected {{ color: {c.ACCENT}; }}

    /* ── ToolTip ── */
    QToolTip {{
        background: {c.SURFACE}; color: {c.TEXT_PRIMARY};
        border: 1px solid {c.SEPARATOR};
        border-radius: 4px; padding: 5px 10px; font-size: 12px;
    }}

    /* ── 菜单 ── */
    QMenu {{
        background: {c.CARD}; border: 1px solid {c.SEPARATOR};
        border-radius: 4px; padding: 4px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 3px; font-size: 13px; }}
    QMenu::item:selected {{ background: {c.ACCENT}; color: #ffffff; }}
    """
