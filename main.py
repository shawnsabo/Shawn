"""CCTRCloud Export Desktop - 入口"""
import sys
from PySide6.QtWidgets import QApplication
from cctr_export.core.database import init_db
from cctr_export.ui import MainWindow, apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CCTRCloud Export Desktop")
    apply_theme(app)
    init_db()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
