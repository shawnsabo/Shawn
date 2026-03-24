"""PySide6 主题系统 - 深色/浅色切换"""
from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication


class LightColors:
    """浅色主题配色 - 清新现代风格"""
    # 背景层次：主背景 → 卡片 → 悬浮
    BG = "#ffffff"           # 白色主背景（干净明亮）
    SURFACE = "#f7f9fc"     # 极浅蓝灰（侧边栏/标题栏）
    CARD = "#ffffff"         # 白色卡片
    CARD_HOVER = "#f0f4ff"   # 浅蓝悬浮态
    BORDER = "#e1e6ef"      # 柔和边框
    TEXT_PRIMARY = "#1a1d24" # 近黑色主文字
    TEXT_SECONDARY = "#6b7280" # 中灰次要文字
    TEXT_DISABLED = "#afb8c1"
    ACCENT = "#3b82f6"      # 鲜亮蓝（按钮/链接）
    ACCENT_HOVER = "#2563eb" # 深蓝（hover）
    ACCENT_LIGHT = "#3b82f615"  # 浅蓝背景
    SUCCESS = "#16a34a"      # 鲜绿
    WARNING = "#d97706"      # 橙色
    ERROR = "#dc2626"       # 鲜红
    INFO = "#3b82f6"        # 蓝色
    SCROLLBAR = "#d1d5db"   # 滚动条
    SCROLLBAR_HOVER = "#9ca3af"
    SIDEBAR = "#f7f9fc"     # 极浅蓝灰侧边栏
    INPUT_BG = "#ffffff"
    PROGRESS_BG = "#e5e7eb"
    SHADOW = "#00000018"    # 柔和阴影


class DarkColors:
    """深色主题配色"""
    BG = "#0d1117"
    SURFACE = "#161b22"
    CARD = "#161b22"
    CARD_HOVER = "#1c2129"
    BORDER = "#30363d"
    TEXT_PRIMARY = "#e6edf3"
    TEXT_SECONDARY = "#8b949e"
    TEXT_DISABLED = "#484f58"
    ACCENT = "#58a6ff"
    ACCENT_HOVER = "#79c0ff"
    ACCENT_LIGHT = "#58a6ff22"
    SUCCESS = "#3fb950"
    WARNING = "#d29922"
    ERROR = "#f85149"
    INFO = "#58a6ff"
    SCROLLBAR = "#30363d"
    SCROLLBAR_HOVER = "#484f58"
    SIDEBAR = "#0d1117"
    INPUT_BG = "#0d1117"
    PROGRESS_BG = "#30363d"
    SHADOW = "#00000040"


# ── 全局状态 ──────────────────────────────────
_dark_mode = True


class _ColorsProxy:
    """动态颜色代理，支持 Colors.XXX 写法，切换主题时自动更新"""
    _current = DarkColors

    def __getattr__(self, name):
        return getattr(self._current, name)


Colors = _ColorsProxy()  # 外部用 Colors.XXX


def is_dark() -> bool:
    return _dark_mode


def get_colors():
    return Colors


def set_dark(dark: bool):
    global _dark_mode
    _dark_mode = dark
    Colors._current = DarkColors if dark else LightColors


def apply_theme(app: QApplication):
    c = Colors
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(c.BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(c.CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c.SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.CARD))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(c.CARD))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(c.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c.TEXT_DISABLED))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c.TEXT_DISABLED))
    app.setPalette(palette)
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    app.setStyleSheet(_stylesheet(c))


def _stylesheet(c) -> str:
    return f"""
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c.SCROLLBAR};
        min-height: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c.SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: {c.INPUT_BG};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        padding: 8px 12px;
        color: {c.TEXT_PRIMARY};
        selection-background-color: {c.ACCENT};
        min-height: 36px;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border-color: {c.ACCENT};
    }}

    QPushButton {{
        background: {c.ACCENT};
        color: #fff;
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        min-height: 36px;
    }}
    QPushButton:hover {{
        background: {c.ACCENT_HOVER};
    }}
    QPushButton:pressed {{
        background: {c.ACCENT};
    }}
    QPushButton:disabled {{
        background: {c.BORDER};
        color: {c.TEXT_DISABLED};
    }}
    QPushButton[flat="true"] {{
        background: transparent;
        color: {c.ACCENT};
        padding: 8px 12px;
    }}
    QPushButton[flat="true"]:hover {{
        background: {c.ACCENT_LIGHT};
        border-radius: 8px;
    }}

    QTableView, QTableWidget {{
        background: {c.CARD};
        border: 1px solid {c.BORDER};
        border-radius: 12px;
        gridline-color: {c.BORDER};
        selection-background-color: {c.ACCENT_LIGHT};
        selection-color: {c.ACCENT};
    }}
    QHeaderView::section {{
        background: {c.SURFACE};
        color: {c.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {c.BORDER};
        padding: 10px 12px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 8px 12px;
        border-bottom: 1px solid {c.BORDER};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 30px;
    }}
    QComboBox QAbstractItemView {{
        background: {c.CARD};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        selection-background-color: {c.ACCENT};
    }}

    QCheckBox {{
        spacing: 10px;
        color: {c.TEXT_PRIMARY};
        font-size: 13px;
        padding: 4px 6px;
    }}
    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 5px;
        border: 2px solid {c.BORDER};
        background: {c.INPUT_BG};
    }}
    QCheckBox::indicator:checked {{
        background: {c.ACCENT};
        border-color: {c.ACCENT};
    }}
    QCheckBox:hover {{
        color: {c.TEXT_PRIMARY};
        background: {c.CARD_HOVER};
        border-radius: 4px;
    }}

    QProgressBar {{
        background: {c.PROGRESS_BG};
        border: none;
        border-radius: 6px;
        min-height: 8px;
        text-align: center;
        color: {c.TEXT_SECONDARY};
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background: {c.ACCENT};
        border-radius: 6px;
    }}

    QStatusBar {{
        background: {c.SURFACE};
        color: {c.TEXT_SECONDARY};
        border-top: 1px solid {c.BORDER};
        font-size: 12px;
        padding: 4px 12px;
    }}

    QTabWidget::pane {{
        border: 1px solid {c.BORDER};
        border-radius: 12px;
        background: {c.CARD};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c.TEXT_SECONDARY};
        padding: 10px 20px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: {c.ACCENT};
        border-bottom: 2px solid {c.ACCENT};
    }}
    """
