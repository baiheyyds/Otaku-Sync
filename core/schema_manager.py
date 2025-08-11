# core/schema_manager.py
# 该模块用于在运行时发现并缓存 Notion 数据库的结构 (Schema)
from typing import Dict

from utils import logger

class NotionSchemaManager:
    def __init__(self, notion_client):
        self._notion_client = notion_client
        self._schemas: Dict[str, Dict[str, str]] = {}

    async def initialize_schema(self, db_id: str, db_name: str):
        """获取并缓存指定数据库的 Schema"""
        logger.system(f"正在获取 {db_name} 数据库的结构...")
        schema_data = await self._notion_client.get_database_schema(db_id)
        if not schema_data:
            logger.error(f"无法获取 {db_name} 的数据库结构，动态属性功能将受限。")
            self._schemas[db_id] = {}
            return

        prop_map = {}
        for prop_name, prop_data in schema_data.get("properties", {}).items():
            prop_map[prop_name] = prop_data.get("type")
        
        self._schemas[db_id] = prop_map
        logger.success(f"已成功缓存 {db_name} 数据库结构，共 {len(prop_map)} 个属性。")

    def get_property_type(self, db_id: str, prop_name: str) -> str | None:
        """根据属性名获取其在 Notion 中的类型"""
        return self._schemas.get(db_id, {}).get(prop_name)