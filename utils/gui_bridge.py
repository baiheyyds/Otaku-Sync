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
    confirm_brand_merge_requested = Signal(str, str)

    # Signals for the newly refactored interactions
    select_game_requested = Signal(list, str, str)
    duplicate_check_requested = Signal(list)

    def __init__(self, loop, parent=None):
        super().__init__(parent)
        self.loop = loop
        self.current_future = None

    def get_response_future(self):
        """Creates and returns a new future for the current interaction."""
        self.current_future = self.loop.create_future()
        return self.current_future

    async def get_bangumi_game_choice(self, game_name: str, candidates: list) -> str | None:
        self.select_bangumi_game_requested.emit(game_name, candidates)
        return await self.get_response_future()

    async def get_tag_translation(self, tag: str, source_name: str) -> str:
        self.tag_translation_required.emit(tag, source_name)
        return await self.get_response_future()

    async def get_concept_merge_decision(self, concept: str, candidate: str) -> str | None:
        self.concept_merge_required.emit(concept, candidate)
        return await self.get_response_future()

    async def get_name_split_decision(self, text: str, parts: list) -> dict:
        self.name_split_decision_required.emit(text, parts)
        return await self.get_response_future()

    async def confirm_brand_merge(self, new_brand_name: str, suggested_brand: str) -> str:
        self.confirm_brand_merge_requested.emit(new_brand_name, suggested_brand)
        return await self.get_response_future()

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        self.ask_for_new_property_type_requested.emit({"prop_name": prop_name})
        return await self.get_response_future()

    async def handle_new_bangumi_key(self, request_data: dict) -> dict:
        self.handle_new_bangumi_key_requested.emit(request_data)
        return await self.get_response_future()

    # --- Implementation for the newly refactored methods ---
    async def select_game(self, choices: list, title: str, source: str) -> int | str | None:
        self.select_game_requested.emit(choices, title, source)
        return await self.get_response_future()

    async def confirm_duplicate(self, candidates: list) -> str | None:
        self.duplicate_check_requested.emit(candidates)
        return await self.get_response_future()

    def set_response(self, response):
        if self.current_future and not self.current_future.done():
            self.current_future.set_result(response)
