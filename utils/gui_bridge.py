# utils/gui_bridge.py
import asyncio
from abc import ABCMeta
from PySide6.QtCore import QObject, Signal
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
    """GUI implementation for user interaction using Qt signals and asyncio.Future."""
    handle_new_bangumi_key_requested = Signal(dict)
    ask_for_new_property_type_requested = Signal(dict)
    select_bangumi_game_requested = Signal(str, list)
    tag_translation_required = Signal(str, str)
    concept_merge_required = Signal(str, str)
    name_split_decision_required = Signal(str, list)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__()
        if not loop:
            raise ValueError("An asyncio event loop is required.")
        self._loop = loop
        self._future: asyncio.Future = None

    def set_response(self, response: Any):
        """Called by the GUI thread to provide the user's choice."""
        if self._future and not self._future.done():
            # Use call_soon_threadsafe to safely set the result from another thread
            self._loop.call_soon_threadsafe(self._future.set_result, response)

    async def _wait_for_response(self, timeout=300):
        """Helper to wait for the response from the GUI thread using asyncio.Future."""
        if self._future and not self._future.done():
            project_logger.warn("交互请求冲突：上一个请求尚未完成。")
            self._future.cancel()

        self._future = self._loop.create_future()
        try:
            return await asyncio.wait_for(self._future, timeout=timeout)
        except asyncio.TimeoutError:
            project_logger.error(f"等待GUI响应超时（{timeout}秒），操作被强制取消。")
            return None
        except asyncio.CancelledError:
            project_logger.warn("交互操作被取消。")
            return None
        finally:
            self._future = None

    async def handle_new_bangumi_key(
        self,
        bangumi_key: str,
        bangumi_value: Any,
        bangumi_url: str,
        db_name: str,
        mappable_props: List[str],
        recommended_props: List[str] = None,
    ) -> Dict[str, Any]:
        request_data = {
            "bangumi_key": bangumi_key,
            "bangumi_value": bangumi_value,
            "bangumi_url": bangumi_url,
            "db_name": db_name,
            "mappable_props": mappable_props,
            "recommended_props": recommended_props or [],
        }
        self.handle_new_bangumi_key_requested.emit(request_data)
        response = await self._wait_for_response()
        return response or {"action": "ignore_session"}

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        self.ask_for_new_property_type_requested.emit({"prop_name": prop_name})
        response = await self._wait_for_response()
        return response

    async def get_bangumi_game_choice(self, search_term: str, candidates: List[Dict]) -> str | None:
        project_logger.system("[Bridge] Emitting select_bangumi_game_requested signal.")
        self.select_bangumi_game_requested.emit(search_term, candidates)
        response = await self._wait_for_response()
        return response

    async def get_tag_translation(self, tag: str, source_name: str) -> str | None:
        self.tag_translation_required.emit(tag, source_name)
        response = await self._wait_for_response()
        return response

    async def get_concept_merge_choice(self, concept: str, candidate: str) -> str | None:
        self.concept_merge_required.emit(concept, candidate)
        response = await self._wait_for_response()
        return response

    async def get_name_split_decision(self, text: str, parts: list) -> dict:
        self.name_split_decision_required.emit(text, parts)
        response = await self._wait_for_response()
        return response or {"action": "keep", "save_exception": False}
