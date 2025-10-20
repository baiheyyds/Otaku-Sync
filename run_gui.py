import logging
import sys

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from utils.gui_bridge import log_bridge
from utils.logger import setup_logging_for_gui

if __name__ == "__main__":
    # 1. Setup logging for GUI
    # This must be done before any logging calls are made.
    setup_logging_for_gui(log_bridge.log_received)

    app = QApplication(sys.argv)

    # --- Start of Translation Block ---
    translator = QTranslator()
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_zh_CN", translations_path):
        app.installTranslator(translator)
    else:
        if translator.load("qtbase_zh_CN", "translations"):
             app.installTranslator(translator)
        else:
            logging.warning("Could not load Chinese translations for Qt standard dialogs.")
    # --- End of Translation Block ---

    # Load the custom stylesheet
    custom_stylesheet = ""
    try:
        with open("gui/style.qss", "r", encoding="utf-8") as f:
            custom_stylesheet = f.read()
        app.setStyleSheet(custom_stylesheet)
    except FileNotFoundError:
        logging.error("gui/style.qss not found.")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
