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
    select_bangumi_game_requested = Signal(list)
    tag_translation_required = Signal(str, str)
    concept_merge_required = Signal(str, str)
    name_split_decision_required = Signal(str, list)

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

    async def _wait_for_response(self):
        """Helper to wait for the response from the GUI thread."""
        self.mutex.lock()
        try:
            # Set a timeout of 5 minutes for safety
            timed_out = not self.wait_condition.wait(self.mutex, 300000)
            if timed_out:
                project_logger.error("等待GUI响应超时（5分钟），操作被强制取消。")
                return None
            response = self._response
        finally:
            self._response = None  # Reset for next use
            self.mutex.unlock()
        return response

    async def handle_new_bangumi_key(
        self,
        bangumi_key: str,
        bangumi_value: Any,
        bangumi_url: str,
        db_name: str,
        mappable_props: List[str],
    ) -> Dict[str, Any]:
        request_data = {
            "bangumi_key": bangumi_key,
            "bangumi_value": bangumi_value,
            "bangumi_url": bangumi_url,
            "db_name": db_name,
            "mappable_props": mappable_props,
        }
        # Emit signal before locking
        self.handle_new_bangumi_key_requested.emit(request_data)
        # Wait for the response
        response = await self._wait_for_response()
        # Default to ignore_session if GUI fails or times out
        return response or {"action": "ignore_session"}

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        # Emit signal before locking
        self.ask_for_new_property_type_requested.emit({"prop_name": prop_name})
        # Wait for the response
        response = await self._wait_for_response()
        return response

    async def get_bangumi_game_choice(self, candidates: List[Dict]) -> str | None:
        """Asks the user to select a game from a list of candidates via the GUI."""
        project_logger.system("[Bridge] Emitting select_bangumi_game_requested signal.")
        self.select_bangumi_game_requested.emit(candidates)
        response = await self._wait_for_response()
        return response

    async def get_tag_translation(self, tag: str, source_name: str) -> str | None:
        """Asks for a translation for a new tag."""
        self.tag_translation_required.emit(tag, source_name)
        response = await self._wait_for_response()
        return response

    async def get_concept_merge_choice(self, concept: str, candidate: str) -> str | None:
        """Asks the user whether to merge a new tag concept."""
        self.concept_merge_required.emit(concept, candidate)
        response = await self._wait_for_response()
        return response

    async def get_name_split_decision(self, text: str, parts: list) -> dict:
        """Asks the user to decide on a risky name split."""
        self.name_split_decision_required.emit(text, parts)
        response = await self._wait_for_response()
        return response or {"action": "keep", "save_exception": False} # Default to keeping original
