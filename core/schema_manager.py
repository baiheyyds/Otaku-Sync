# core/schema_manager.py
from typing import Dict, List

from utils import logger


class NotionSchemaManager:
    def __init__(self, notion_client):
        self._notion_client = notion_client
        # 1. 修改类型提示，值的类型不再是 str，而是 Dict
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

    async def initialize_schema(self, db_id: str, db_name: str):
        """获取并缓存指定数据库的 Schema"""
        logger.system(f"正在获取 {db_name} 数据库的结构...")
        schema_data = await self._notion_client.get_database_schema(db_id)
        if not schema_data:
            logger.error(f"无法获取 {db_name} 的数据库结构，动态属性功能将受限。")
            self._schemas[db_id] = {}
            return

        prop_map = {}
        # 2. 修改这里的逻辑：直接保存完整的 prop_data 字典
        for prop_name, prop_data in schema_data.get("properties", {}).items():
            prop_map[prop_name] = prop_data  # <--- 修改这行代码

        self._schemas[db_id] = prop_map
        logger.success(f"已成功缓存 {db_name} 数据库结构，共 {len(prop_map)} 个属性。")

    def get_property_type(self, db_id: str, prop_name: str) -> str | None:
        """根据属性名获取其在 Notion 中的类型"""
        # 3. 修改这里的逻辑，以适应新的数据结构
        schema = self._schemas.get(db_id, {})
        prop_info = schema.get(prop_name)  # 现在 prop_info 是一个字典
        if prop_info and isinstance(prop_info, dict):
            return prop_info.get("type")
        return None

    # 4. (可选但推荐) 确保你的 get_schema 方法返回的是正确的结构
    def get_schema(self, db_id: str) -> Dict[str, Dict] | None:
        """获取指定数据库的完整 schema 缓存"""
        return self._schemas.get(db_id)

    def get_mappable_properties(self, db_id: str) -> List[str]:
        """获取指定数据库中所有可用于映射的属性名称列表"""
        schema = self._schemas.get(db_id, {})
        mappable_props = [
            name
            for name, prop_info in schema.items()  # prop_info 现在是字典
            if prop_info.get("type") not in self._non_mappable_types
        ]
        return sorted(mappable_props)
