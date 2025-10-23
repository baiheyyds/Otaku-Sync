# gui/image_loader.py
import logging
from PySide6.QtCore import (QObject, QRunnable, QThreadPool, Signal, Slot, Qt)
from PySide6.QtGui import QIcon, QPixmap, QPainter
import requests

# --- Constants and Cache ---
ICON_WIDTH = 150
ICON_HEIGHT = 200
PLACEHOLDER_ICON = None
IMAGE_CACHE = {}

def get_placeholder_icon():
    """Creates and caches a placeholder icon."""
    global PLACEHOLDER_ICON
    if PLACEHOLDER_ICON is None:
        pixmap = QPixmap(ICON_WIDTH, ICON_HEIGHT)
        pixmap.fill(Qt.GlobalColor.gray)
        PLACEHOLDER_ICON = QIcon(pixmap)
    return PLACEHOLDER_ICON

# --- Downloader Worker ---
class ImageDownloaderSignals(QObject):
    finished = Signal(str, QPixmap)
    error = Signal(str, str)

class ImageDownloader(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = ImageDownloaderSignals()

    @Slot()
    def run(self):
        if self.url in IMAGE_CACHE:
            self.signals.finished.emit(self.url, IMAGE_CACHE[self.url])
            return
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(self.url, timeout=15, headers=headers)
            response.raise_for_status()
            
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            
            if not pixmap.isNull():
                IMAGE_CACHE[self.url] = pixmap
                self.signals.finished.emit(self.url, pixmap)
            else:
                raise ValueError("Failed to load image from data")
        except Exception as e:
            logging.warning(f"Image download error for {self.url}: {e}")
            self.signals.error.emit(self.url, str(e))

# --- Loader Manager ---
class ImageLoader(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(5) # Limit concurrent downloads to 5

    def load_image(self, url, on_finish_callback, on_error_callback=None):
        if not url or not url.startswith('http'):
            return
            
        downloader = ImageDownloader(url)
        downloader.signals.finished.connect(on_finish_callback)
        if on_error_callback:
            downloader.signals.error.connect(on_error_callback)
            
        self.thread_pool.start(downloader)
