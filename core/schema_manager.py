# core/schema_manager.py
from typing import Dict, List

from utils import logger


class NotionSchemaManager:
    def __init__(self, notion_client):
        self._notion_client = notion_client
        self._schemas: Dict[str, Dict[str, str]] = {}
        # 增加一个不可用作映射目标的属性类型集合
        self._non_mappable_types = {
            "formula",
            "rollup",
            "relation",
            "created_time",
            "created_by",
            "last_edited_time",
            "last_edited_by",
        }

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

    # --- 新增方法 ---
    def get_mappable_properties(self, db_id: str) -> List[str]:
        """获取指定数据库中所有可用于映射的属性名称列表"""
        schema = self._schemas.get(db_id, {})
        mappable_props = [
            name
            for name, type in schema.items()
            if type not in self._non_mappable_types
        ]
        return sorted(mappable_props)