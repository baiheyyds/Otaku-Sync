
import sys
import qdarkstyle
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Load the dark theme stylesheet first
    dark_stylesheet = qdarkstyle.load_stylesheet(qt_api='pyside6')

    # Load the custom stylesheet
    custom_stylesheet = ""
    try:
        with open("gui/style.qss", "r", encoding="utf-8") as f:
            custom_stylesheet = f.read()
    except FileNotFoundError:
        # This is a fallback in case the file is missing, but it shouldn't be.
        pass

    # Combine both stylesheets
    app.setStyleSheet(dark_stylesheet + custom_stylesheet)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
