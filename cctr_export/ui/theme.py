"""PySide6 主题系统 — 深空美学 · OKLCH-inspired"""
from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication


# ──────────────────────────────────────────────────────────────────
# 深空美学配色（深色主题）
# 灵感：深空蓝 + 青色高光 · 专业工具感
# ──────────────────────────────────────────────────────────────────

class LightColors:
    """浅色主题 — 温暖中性灰"""
    BG          = "#FAFAF9"   # 暖白主背景
    SURFACE     = "#F5F4F2"   # 暖灰表面
    CARD        = "#FFFFFF"
    CARD_HOVER  = "#F0F0EE"
    BORDER      = "#E5E4E2"
    TEXT_PRIMARY   = "#18181B"   # 近黑（温暖）
    TEXT_SECONDARY = "#71717A"   # 中性灰
    TEXT_DISABLED  = "#A1A1AA"
    # OKLCH-inspired accent: L=50% C=18% h=230° → 近似 hex
    ACCENT      = "#6366F1"      # 靛蓝（OKLCH-inspired）
    ACCENT_HOVER= "#4F46E5"
    ACCENT_LIGHT= "#6366F120"
    SUCCESS     = "#10B981"      # 翠绿
    WARNING     = "#F59E0B"
    ERROR       = "#EF4444"
    INFO        = "#3B82F6"
    SCROLLBAR       = "#D4D4D4"
    SCROLLBAR_HOVER = "#A3A3A3"
    SIDEBAR     = "#F5F4F2"
    INPUT_BG    = "#FFFFFF"
    PROGRESS_BG = "#E5E4E2"
    SHADOW      = "#00000018"
    SHADOW_ACCENT = "#6366F130"

    # 渐变（用于按钮背景）
    GRADIENT_PRIMARY_START = "#818CF8"
    GRADIENT_PRIMARY_END   = "#6366F1"


class DarkColors:
    """深色主题 — 深空美学"""
    BG          = "#0B0B10"   # 深空黑（微蓝底）
    SURFACE     = "#13131A"   # 深蓝灰
    CARD        = "#1A1A26"   # 卡片（微紫）
    CARD_HOVER  = "#22223A"   # 悬浮态
    BORDER      = "#2A2A3C"   # 边框（微紫）
    TEXT_PRIMARY   = "#F4F4F5"   # 亮白
    TEXT_SECONDARY = "#A1A1AA"   # 中灰
    TEXT_DISABLED  = "#52525B"
    # OKLCH-inspired accent: L=55% C=35% h=265°
    ACCENT      = "#818CF8"      # 浅靛蓝（比亮色更柔和）
    ACCENT_HOVER= "#A5B4FC"      # hover 时更亮
    ACCENT_LIGHT= "#818CF820"
    SUCCESS     = "#34D399"      # 亮绿
    WARNING     = "#FBBF24"
    ERROR       = "#F87171"
    INFO        = "#60A5FA"
    SCROLLBAR       = "#2A2A3C"
    SCROLLBAR_HOVER = "#3F3F56"
    SIDEBAR     = "#0B0B10"
    INPUT_BG    = "#13131A"
    PROGRESS_BG = "#2A2A3C"
    SHADOW      = "#00000050"
    SHADOW_ACCENT = "#818CF840"

    # 渐变
    GRADIENT_PRIMARY_START = "#A5B4FC"
    GRADIENT_PRIMARY_END   = "#818CF8"


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


def apply_theme(app: QApplication):
    c = Colors

    # 字体
    font = QFont("Segoe UI Variable", 10)
    if not font.exactMatch():
        font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Palette
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
    app.setStyleSheet(_stylesheet(c))


def _stylesheet(c) -> str:
    return f"""
    /* ── 滚动条 ── */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 6px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c.SCROLLBAR};
        min-height: 40px;
        border-radius: 3px;
        margin: 2px 1px;
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
    QScrollBar:horizontal {{
        border: none;
        background: transparent;
        height: 6px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {c.SCROLLBAR};
        min-width: 40px;
        border-radius: 3px;
        margin: 1px 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c.SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ── 输入框 ── */
    QLineEdit, QTextEdit, QComboBox, QSpinBox {{
        background: {c.INPUT_BG};
        border: 1.5px solid {c.BORDER};
        border-radius: 10px;
        padding: 10px 14px;
        color: {c.TEXT_PRIMARY};
        selection-background-color: {c.ACCENT};
        min-height: 38px;
        font-size: 14px;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border-color: {c.ACCENT};
        background: {c.CARD};
    }}
    QLineEdit::placeholder, QTextEdit::placeholder {{
        color: {c.TEXT_DISABLED};
    }}

    /* ── 按钮（主）─ */
    QPushButton {{
        background: {c.ACCENT};
        color: #fff;
        border: none;
        border-radius: 10px;
        padding: 10px 20px;
        font-weight: 600;
        font-size: 14px;
        min-height: 38px;
        letter-spacing: 0.2px;
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
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton[flat="true"]:hover {{
        background: {c.ACCENT_LIGHT};
        border-radius: 10px;
    }}

    /* ── 表格 ── */
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
        padding: 10px 14px;
        font-weight: 600;
        font-size: 12px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }}
    QTableWidget::item {{
        padding: 10px 14px;
        border-bottom: 1px solid {c.BORDER};
        font-size: 13px;
    }}
    QTableWidget::item:hover {{
        background: {c.CARD_HOVER};
    }}

    /* ── 下拉框 ── */
    QComboBox::drop-down {{
        border: none;
        width: 32px;
    }}
    QComboBox QAbstractItemView {{
        background: {c.CARD};
        border: 1px solid {c.BORDER};
        border-radius: 10px;
        selection-background-color: {c.ACCENT};
        padding: 4px;
    }}
    QComboBox QAbstractItemView::item {{
        border-radius: 6px;
        padding: 6px 10px;
    }}

    /* ── 复选框 ── */
    QCheckBox {{
        spacing: 10px;
        color: {c.TEXT_PRIMARY};
        font-size: 14px;
        padding: 4px 6px;
    }}
    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 2px solid {c.BORDER};
        background: {c.INPUT_BG};
    }}
    QCheckBox::indicator:checked {{
        background: {c.ACCENT};
        border-color: {c.ACCENT};
    }}
    QCheckBox:hover {{
        color: {c.TEXT_PRIMARY};
    }}

    /* ── 进度条 ── */
    QProgressBar {{
        background: {c.PROGRESS_BG};
        border: none;
        border-radius: 6px;
        min-height: 8px;
        text-align: center;
        color: transparent;
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        background: {c.ACCENT};
        border-radius: 6px;
    }}

    /* ── 状态栏 ── */
    QStatusBar {{
        background: {c.SURFACE};
        color: {c.TEXT_SECONDARY};
        border-top: 1px solid {c.BORDER};
        font-size: 12px;
        padding: 4px 16px;
    }}

    /* ── Tab ── */
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
    QTabBar::tab:hover:!selected {{
        color: {c.TEXT_PRIMARY};
    }}

    /* ── ToolTip ── */
    QToolTip {{
        background: {c.SURFACE};
        color: {c.TEXT_PRIMARY};
        border: 1px solid {c.BORDER};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    """
