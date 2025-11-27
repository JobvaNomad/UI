# main.py
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from PyQt6.QtGui import QIcon

from chat_window import ChatWindow


def main():
    app = QApplication(sys.argv)
    window = ChatWindow()

    icon_path = Path(__file__).with_name("app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window.show()
    window.input_line.setFocus()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
