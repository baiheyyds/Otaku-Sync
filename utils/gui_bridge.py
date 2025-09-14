# utils/gui_bridge.py
from abc import ABCMeta
from PySide6.QtCore import QObject, Signal, QMutex, QWaitCondition
from utils import logger as project_logger
from core.interaction import InteractionProvider
from typing import Any, Dict, List

class _LogBridge(QObject):
    """ A bridge to forward logs from the custom logger to the GUI. """ 
    log_received = Signal(str)

# Global instance of the bridge
log_bridge = _LogBridge()

def patch_logger():
    """
    Dynamically replaces the print-based functions in the project's custom
    logger with functions that emit a Qt signal.
    """
    
    # --- Define new functions that emit signals --- #
    def new_step(message):
        log_bridge.log_received.emit(f"🚀 {message}")

    def new_info(message):
        log_bridge.log_received.emit(f"🔍 {message}")

    def new_success(message):
        log_bridge.log_received.emit(f"✅ {message}")

    def new_warn(message):
        log_bridge.log_received.emit(f"⚠️ {message}")

    def new_error(message):
        log_bridge.log_received.emit(f"❌ {message}")

    def new_system(message):
        log_bridge.log_received.emit(f"🔧 {message}")

    def new_cache(message):
        log_bridge.log_received.emit(f"🗂️ {message}")

    def new_result(message):
        # For multi-line results, emit as is
        log_bridge.log_received.emit(str(message))

    # --- Apply the patches --- #
    project_logger.step = new_step
    project_logger.info = new_info
    project_logger.success = new_success
    project_logger.warn = new_warn
    project_logger.error = new_error
    project_logger.system = new_system
    project_logger.cache = new_cache
    project_logger.result = new_result

    new_system("日志系统已成功接入GUI。后台终端将不再有重复输出。")

# Metaclass to resolve conflict between QObject and ABC
class QObjectABCMeta(type(QObject), ABCMeta):
    pass

class GuiInteractionProvider(QObject, InteractionProvider, metaclass=QObjectABCMeta):
    """GUI implementation for user interaction using Qt signals."""
    handle_new_bangumi_key_requested = Signal(dict)
    ask_for_new_property_type_requested = Signal(dict)

    def __init__(self):
        super().__init__()
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        self._response = None

    def set_response(self, response: Any):
        """Called by the GUI thread to provide the user's choice."""
        self.mutex.lock()
        self._response = response
        self.mutex.unlock()
        self.wait_condition.wakeAll()

    async def handle_new_bangumi_key(
        self,
        bangumi_key: str,
        bangumi_value: Any,
        bangumi_url: str,
        db_name: str,
        mappable_props: List[str],
    ) -> Dict[str, Any]:
        self.mutex.lock()
        request_data = {
            "bangumi_key": bangumi_key,
            "bangumi_value": bangumi_value,
            "bangumi_url": bangumi_url,
            "db_name": db_name,
            "mappable_props": mappable_props,
        }
        self.handle_new_bangumi_key_requested.emit(request_data)
        self.wait_condition.wait(self.mutex)
        response = self._response
        self._response = None  # Reset for next use
        self.mutex.unlock()
        return response

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        self.mutex.lock()
        self.ask_for_new_property_type_requested.emit({"prop_name": prop_name})
        self.wait_condition.wait(self.mutex)
        response = self._response
        self._response = None # Reset for next use
        self.mutex.unlock()
        return response

    async def get_bangumi_game_choice(self, candidates: List[Dict]) -> int | str:
        # This part is handled by the existing selection dialog in the GUI worker,
        # so we don't need a complex implementation here. This is a slight
        # divergence from a pure provider model but avoids re-implementing
        # the existing GUI flow.
        pass
