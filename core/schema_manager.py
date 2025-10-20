# core/schema_manager.py
import asyncio
import json
import logging
import os
import time
from typing import Dict, List

CACHE_DIR = "cache"
SCHEMA_CACHE_FILE = os.path.join(CACHE_DIR, "notion_schemas_cache.json")
CACHE_EXPIRATION = 86400  # 24 hours in seconds


class NotionSchemaManager:
    def __init__(self, notion_client):
        self._notion_client = notion_client
        self._schemas: Dict[str, Dict[str, Dict]] = {}
        self._non_mappable_types = {
            "formula",
            "rollup",
            "relation",
            "created_time",
            "created_by",
            "last_edited_time",
            "last_edited_by",
        }
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _load_schemas_from_cache(self) -> bool:
        if not os.path.exists(SCHEMA_CACHE_FILE):
            return False
        if time.time() - os.path.getmtime(SCHEMA_CACHE_FILE) > CACHE_EXPIRATION:
            logging.info("🗂️ Notion schema 缓存已过期。")
            return False
        try:
            with open(SCHEMA_CACHE_FILE, "r", encoding="utf-8") as f:
                self._schemas = json.load(f)
                logging.info(f"🗂️ 已成功从缓存加载 {len(self._schemas)} 个 Notion 数据库结构。")
                return True
        except (json.JSONDecodeError, IOError) as e:
            logging.warning(f"⚠️ 加载 Notion schema 缓存失败: {e}")
            return False

    # --- [核心修改 1] ---
    # 将 _save_schemas_to_cache 重命名为 save_schemas_to_cache，使其成为公共方法
    def save_schemas_to_cache(self):
        """将当前内存中的数据库结构写入缓存文件。"""
        try:
            with open(SCHEMA_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._schemas, f, ensure_ascii=False, indent=2)
            logging.info("🗂️ 已将最新的 Notion 数据库结构写入缓存。")
        except IOError as e:
            logging.error(f"❌ 保存 Notion schema 缓存失败: {e}")

    # --- [修改结束] ---

    async def initialize_schema(self, db_id: str, db_name: str):
        # 这个方法现在只负责获取和更新内存中的schema，不再负责保存
        # if db_id in self._schemas: # 移除这个检查，允许强制刷新
        #     return
        logging.info(f"🔧 正在获取或刷新 {db_name} 数据库的结构...")
        schema_data = await self._notion_client.get_database_schema(db_id)
        if not schema_data:
            logging.error(f"❌ 无法获取 {db_name} 的数据库结构，动态属性功能将受限。")
            self._schemas[db_id] = None  # Store None to indicate failure
            return
        prop_map = {
            prop_name: prop_data
            for prop_name, prop_data in schema_data.get("properties", {}).items()
        }
        self._schemas[db_id] = prop_map
        logging.info(f"✅ 已成功缓存 {db_name} 数据库结构，共 {len(prop_map)} 个属性。")

    async def load_all_schemas(self, db_configs: dict):
        if self._load_schemas_from_cache():
            return
        logging.info("🔧 缓存无效或过期，正在从 Notion API 获取数据库结构...")
        tasks = [self.initialize_schema(db_id, db_name) for db_id, db_name in db_configs.items()]
        await asyncio.gather(*tasks)

        # --- [核心修改 2] ---
        # 更新对新公共方法的调用
        self.save_schemas_to_cache()
        # --- [修改结束] ---


    def get_property_type(self, db_id: str | None, prop_name: str) -> str | None:
        if not db_id:
            return None
        schema = self._schemas.get(db_id, {})
        prop_info = schema.get(prop_name)
        if prop_info and isinstance(prop_info, dict):
            return prop_info.get("type")
        return None

    def get_schema(self, db_id: str) -> Dict[str, Dict] | None:
        return self._schemas.get(db_id)

    def get_mappable_properties(self, db_id: str) -> List[str]:
        schema = self._schemas.get(db_id, {})
        mappable_props = [
            name
            for name, prop_info in schema.items()
            if prop_info.get("type") not in self._non_mappable_types
        ]
        return sorted(mappable_props)
