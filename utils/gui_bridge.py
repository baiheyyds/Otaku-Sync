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

    def __init__(self, loop, parent=None):
        super().__init__(parent)
        self.loop = loop
        self.future = None

    async def get_bangumi_game_choice(self, game_name: str, candidates: list) -> str | None:
        self.future = self.loop.create_future()
        self.select_bangumi_game_requested.emit(game_name, candidates)
        return await self.future

    async def get_tag_translation(self, tag: str, source_name: str) -> str:
        self.future = self.loop.create_future()
        self.tag_translation_required.emit(tag, source_name)
        return await self.future

    async def get_concept_merge_decision(self, concept: str, candidate: str) -> str | None:
        self.future = self.loop.create_future()
        self.concept_merge_required.emit(concept, candidate)
        return await self.future

    async def get_name_split_decision(self, text: str, parts: list) -> dict:
        self.future = self.loop.create_future()
        self.name_split_decision_required.emit(text, parts)
        return await self.future

    async def confirm_brand_merge(self, new_brand_name: str, suggested_brand: str) -> str:
        """当发现一个新品牌与一个现有品牌高度相似时，询问用户如何操作。"""
        self.future = self.loop.create_future()
        self.confirm_brand_merge_requested.emit(new_brand_name, suggested_brand)
        return await self.future

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        self.future = self.loop.create_create()
        self.ask_for_new_property_type_requested.emit({"prop_name": prop_name})
        return await self.future

    async def handle_new_bangumi_key(self, db_type: str, prop_name: str, prop_value: str, page_id: str) -> dict:
        request_data = {
            "db_type": db_type,
            "prop_name": prop_name,
            "prop_value": prop_value,
            "page_id": page_id,
        }
        self.future = self.loop.create_future()
        self.handle_new_bangumi_key_requested.emit(request_data)
        return await self.future

    def set_response(self, response):
        if self.future and not self.future.done():
            self.future.set_result(response)
