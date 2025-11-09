# utils/logger.py
import logging
import os
from logging import Handler, LogRecord

from rich.logging import RichHandler


# 1. Define the custom handler for GUI
class QtLogHandler(Handler):
    """
    A custom logging handler that emits a Qt signal.
    The signal is defined in gui_bridge.py and connected in MainWindow.
    """
    def __init__(self, signal_emitter):
        super().__init__()
        self.signal_emitter = signal_emitter

    def emit(self, record: LogRecord):
        """
        Emits a Qt signal with the formatted log message.
        The actual formatting is controlled by the formatter set on this handler.
        """
        msg = self.format(record)
        self.signal_emitter.emit(msg)

# 2. Define a shared, simple formatter
# RichHandler will add extra info like time, level, and path based on its own config.
gui_formatter = logging.Formatter("{message}", style="{")
cli_formatter = logging.Formatter("{message}", datefmt="[%X]", style="{")

# 3. Define setup functions
def setup_logging_for_cli(level=None):
    """
    Configures the root logger for CLI output using RichHandler.
    Log level is controlled by the LOG_LEVEL environment variable.
    """
    # Determine log level from environment variable or argument, defaulting to INFO
    if level is None:
        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
    else:
        log_level = level

    log = logging.getLogger()
    log.setLevel(log_level)

    # Remove any existing handlers to avoid duplicates
    if log.hasHandlers():
        log.handlers.clear()

    is_debug = (log_level <= logging.DEBUG)

    rich_handler = RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=is_debug, # Show locals only in debug mode
        log_time_format="[%X]",
        show_path=is_debug  # KEY CHANGE: Only show path in debug mode
    )
    rich_handler.setFormatter(cli_formatter)
    log.addHandler(rich_handler)

    # Set httpx logger to a higher level to avoid verbose request/response logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Suppress verbose logs from webdriver_manager
    logging.getLogger("webdriver_manager").setLevel(logging.ERROR)

    logging.debug("日志系统已初始化 (CLI 模式)。")

def setup_logging_for_gui(qt_signal_emitter, level=logging.INFO):
    """
    Configures the root logger for GUI output using the custom QtLogHandler.
    """
    log = logging.getLogger()
    log.setLevel(level)

    # Remove any existing handlers
    if log.hasHandlers():
        log.handlers.clear()

    qt_handler = QtLogHandler(signal_emitter=qt_signal_emitter)
    qt_handler.setFormatter(gui_formatter)
    log.addHandler(qt_handler)

    # Set httpx logger to a higher level to avoid verbose request/response logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Suppress verbose logs from webdriver_manager
    logging.getLogger("webdriver_manager").setLevel(logging.ERROR)

    logging.info("🔧 日志系统已成功接入GUI。")
