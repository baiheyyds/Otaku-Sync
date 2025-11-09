# gui/image_loader.py
import hashlib
import logging
import os

import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap

# --- Constants and Cache ---
ICON_WIDTH = 150
ICON_HEIGHT = 200
PLACEHOLDER_ICON = None
IMAGE_CACHE = {} # In-memory cache

# --- [新增] 磁盘缓存设置 ---
DISK_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "images")
os.makedirs(DISK_CACHE_DIR, exist_ok=True)
# --- [新增结束] ---

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
        # 检查内存缓存
        if self.url in IMAGE_CACHE:
            self.signals.finished.emit(self.url, IMAGE_CACHE[self.url])
            return

        # --- [核心修改] 检查磁盘缓存 ---
        try:
            # 使用 URL 的哈希值作为安全的文件名
            filename = hashlib.sha256(self.url.encode()).hexdigest()
            cache_filepath = os.path.join(DISK_CACHE_DIR, filename)

            if os.path.exists(cache_filepath):
                pixmap = QPixmap()
                if pixmap.load(cache_filepath):
                    IMAGE_CACHE[self.url] = pixmap # 加载到内存缓存
                    self.signals.finished.emit(self.url, pixmap)
                    return # 缓存命中，结束
        except Exception as e:
            logging.warning(f"检查或加载磁盘缓存时出错: {e}")
        # --- [修改结束] ---

        # 如果缓存未命中，则从网络下载
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(self.url, timeout=15, headers=headers)
            response.raise_for_status()

            pixmap = QPixmap()
            pixmap.loadFromData(response.content)

            if not pixmap.isNull():
                IMAGE_CACHE[self.url] = pixmap
                # --- [新增] 保存到磁盘缓存 ---
                try:
                    with open(cache_filepath, 'wb') as f:
                        f.write(response.content)
                except Exception as e:
                    logging.warning(f"无法将图片写入磁盘缓存 {cache_filepath}: {e}")
                # --- [新增结束] ---
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
