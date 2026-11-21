"""CCTRCloud Export Desktop - 入口"""
import sys
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from cctr_export.core.database import init_db
from cctr_export.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CCTRCloud Export Studio")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    init_db()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
