import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLibraryInfo
from gui.main_window import MainWindow

if __name__ == "__main__":
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
            print("Warning: Could not load Chinese translations for Qt standard dialogs.")
    # --- End of Translation Block ---

    # Load the custom stylesheet
    custom_stylesheet = ""
    try:
        with open("gui/style.qss", "r", encoding="utf-8") as f:
            custom_stylesheet = f.read()
        app.setStyleSheet(custom_stylesheet)
    except FileNotFoundError:
        print("Warning: gui/style.qss not found.")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())