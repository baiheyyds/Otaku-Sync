# core/mapping_manager.py
import asyncio
import json
import logging
import os
from typing import Dict, List

from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID
from utils.similarity_check import get_close_matches_with_ratio
from core.interaction import InteractionProvider
from utils.utils import normalize_brand_name


MAPPING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mapping")
BGM_PROP_MAPPING_PATH = os.path.join(MAPPING_DIR, "bangumi_prop_mapping.json")
BGM_IGNORE_LIST_PATH = os.path.join(MAPPING_DIR, "bangumi_ignore_list.json")
BRAND_MAPPING_PATH = os.path.join(MAPPING_DIR, "brand_mapping.json")

DB_ID_TO_NAMESPACE = {
    GAME_DB_ID: "games",
    CHARACTER_DB_ID: "characters",
    BRAND_DB_ID: "brands",
}

class BrandMappingManager:
    def __init__(self, file_path: str = BRAND_MAPPING_PATH):
        self.file_path = file_path
        self._mapping: Dict[str, List[str]] = {}
        self._reverse_mapping: Dict[str, str] = {}
        self._load_mapping()

    def _load_mapping(self):
        if not os.path.exists(self.file_path):
            logging.warning(f"⚠️ 品牌映射文件不存在: {self.file_path}")
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self._mapping = json.loads(content) if content else {}
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"❌ 加载品牌映射文件失败: {e}")
            self._mapping = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        self._reverse_mapping = {}
        for canonical_name, aliases in self._mapping.items():
            # The canonical name itself is an alias
            normalized_canonical = normalize_brand_name(canonical_name)
            self._reverse_mapping[normalized_canonical] = canonical_name
            for alias in aliases:
                normalized_alias = normalize_brand_name(alias)
                self._reverse_mapping[normalized_alias] = canonical_name

    def get_canonical_name(self, name: str) -> str:
        if not name:
            return ""
        normalized_name = normalize_brand_name(name)
        return self._reverse_mapping.get(normalized_name, name)

    def add_alias(self, canonical_name: str, alias: str):
        """为指定的规范名称添加一个新的别名。"""
        if not canonical_name or not alias:
            return

        # 首先，确保 canonical_name 是我们映射中的一个键
        if canonical_name not in self._mapping:
            # 如果 canonical_name 本身就是一个别名，找到它的根
            true_canonical = self.get_canonical_name(canonical_name)
            if true_canonical != canonical_name: # 找到了根
                canonical_name = true_canonical
            else:
                # 如果它是一个全新的、独立的品牌，则创建一个新条目
                self._mapping[canonical_name] = []

        # 添加新别名（如果它还不存在）
        if alias not in self._mapping[canonical_name] and alias != canonical_name:
            self._mapping[canonical_name].append(alias)
            logging.info(f"🔧 品牌映射学习: ‘{alias}’ -> ‘{canonical_name}’")
        
        # 重建反向映射以立即生效
        self._build_reverse_mapping()

    def save_mapping(self):
        """将当前的品牌映射保存到文件。"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
            logging.info(f"🗂️ 品牌映射文件已成功保存到 {self.file_path}")
        except IOError as e:
            logging.error(f"❌ 保存品牌映射文件失败: {e}")

class BangumiMappingManager:
    def __init__(self, interaction_provider: InteractionProvider, file_path: str = BGM_PROP_MAPPING_PATH):
        self.file_path = file_path
        self.interaction_provider = interaction_provider
        self._mapping: Dict[str, Dict[str, List[str]]] = {}
        self._reverse_mapping: Dict[str, Dict[str, str]] = {}
        self._ignored_keys: set = set()
        self._permanent_ignored_keys: set = set()
        self._interaction_lock = asyncio.Lock()

        self._load_mapping()
        self._load_ignore_list()

    def _load_ignore_list(self):
        if not os.path.exists(BGM_IGNORE_LIST_PATH):
            self._permanent_ignored_keys = set()
            return
        try:
            with open(BGM_IGNORE_LIST_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                self._permanent_ignored_keys = set(json.loads(content) if content else [])
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"❌ 加载 Bangumi 忽略列表文件失败: {e}")
            self._permanent_ignored_keys = set()

    def _load_mapping(self):
        default_structure = {"games": {}, "characters": {}, "brands": {}}
        if not os.path.exists(self.file_path):
            self._mapping = default_structure
        else:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self._mapping = {
                        **default_structure,
                        **(json.loads(content) if content else {}),
                    }
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"❌ 加载 Bangumi 映射文件失败: {e}")
                self._mapping = default_structure
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        self._reverse_mapping = {}
        for namespace, mappings in self._mapping.items():
            self._reverse_mapping[namespace] = {}
            for notion_prop, bangumi_keys in mappings.items():
                for key in bangumi_keys:
                    self._reverse_mapping[namespace][key] = notion_prop

    def get_notion_prop(self, bangumi_key: str, db_id: str) -> str | None:
        if self.is_ignored(bangumi_key):
            return None
        namespace = DB_ID_TO_NAMESPACE.get(db_id)
        if not namespace:
            return None
        return self._reverse_mapping.get(namespace, {}).get(bangumi_key)

    def is_ignored(self, bangumi_key: str) -> bool:
        return bangumi_key in self._ignored_keys or bangumi_key in self._permanent_ignored_keys

    def add_new_mapping(self, bangumi_key: str, notion_prop: str, db_id: str):
        namespace = DB_ID_TO_NAMESPACE.get(db_id)
        if not namespace:
            return

        namespace_mappings = self._mapping.setdefault(namespace, {})
        key_list = namespace_mappings.setdefault(notion_prop, [])
        if bangumi_key not in key_list:
            key_list.append(bangumi_key)

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
        except IOError as e:
            logging.error(f"❌ 保存 Bangumi 映射文件失败: {e}")
            return

        self._reverse_mapping.setdefault(namespace, {})[bangumi_key] = notion_prop
        logging.info(
            f"✅ 已更新【{namespace}】映射表: Bangumi '{bangumi_key}' -> Notion '{notion_prop}'"
        )

    def ignore_key_session(self, bangumi_key: str):
        self._ignored_keys.add(bangumi_key)
        logging.info(f"🔍 属性 '{bangumi_key}' 将在本次运行中被忽略。")

    def _add_to_permanent_ignore_list(self, bangumi_key: str):
        if bangumi_key in self._permanent_ignored_keys:
            return
        self._permanent_ignored_keys.add(bangumi_key)
        try:
            with open(BGM_IGNORE_LIST_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    sorted(list(self._permanent_ignored_keys)), f, ensure_ascii=False, indent=2
                )
            logging.info(f"✅ 已将 '{bangumi_key}' 添加到永久忽略列表。")
        except IOError as e:
            logging.error(f"❌ 保存 Bangumi 永久忽略列表失败: {e}")

    async def _create_and_map_new_property(
        self,
        new_prop_name: str,
        bangumi_key_to_map: str,
        notion_client,
        schema_manager,
        target_db_id: str,
    ) -> str | None:
        
        notion_type = await self.interaction_provider.ask_for_new_property_type(new_prop_name)
        if not notion_type:
            logging.warning(f"⚠️ 未选择属性类型，已取消为 '{new_prop_name}' 创建属性的操作。")
            return None

        success = await notion_client.add_new_property_to_db(
            target_db_id, new_prop_name, notion_type
        )
        if success:
            db_name = DB_ID_TO_NAMESPACE.get(target_db_id, "未知数据库")
            await schema_manager.initialize_schema(target_db_id, db_name)
            self.add_new_mapping(bangumi_key_to_map, new_prop_name, target_db_id)
            return new_prop_name
        return None

    async def handle_new_key(
        self,
        bangumi_key: str,
        bangumi_value: any,
        bangumi_url: str,
        notion_client,
        schema_manager,
        target_db_id: str,
    ) -> str | None:
        async with self._interaction_lock:
            if (
                existing_prop := self.get_notion_prop(bangumi_key, target_db_id)
            ) or self.is_ignored(bangumi_key):
                return existing_prop

            db_name = "未知数据库"
            if namespace := DB_ID_TO_NAMESPACE.get(target_db_id):
                db_name = f"{namespace.capitalize()}数据库"
            
            mappable_props = schema_manager.get_mappable_properties(target_db_id)
            recommended_props = get_close_matches_with_ratio(
                bangumi_key, mappable_props, limit=3, threshold=0.6
            )

            request_data = {
                "bangumi_key": bangumi_key,
                "bangumi_value": bangumi_value,
                "bangumi_url": bangumi_url,
                "db_name": db_name,
                "mappable_props": mappable_props,
                "recommended_props": recommended_props,
            }
            result = await self.interaction_provider.handle_new_bangumi_key(request_data)
            
            action = result.get("action")
            data = result.get("data")

            if action == "map":
                selected_prop = data
                self.add_new_mapping(bangumi_key, selected_prop, target_db_id)
                return selected_prop

            if action == "ignore_session":
                self.ignore_key_session(bangumi_key)
                return None

            if action == "ignore_permanent":
                self._add_to_permanent_ignore_list(bangumi_key)
                return None

            if action == "create_same_name":
                return await self._create_and_map_new_property(
                    bangumi_key, bangumi_key, notion_client, schema_manager, target_db_id
                )

            if action == "create_custom_name":
                if custom_name := data:
                    return await self._create_and_map_new_property(
                        custom_name, bangumi_key, notion_client, schema_manager, target_db_id
                    )
                else:
                    logging.warning("⚠️ 未提供自定义名称，操作已取消。")
                    self.ignore_key_session(bangumi_key)
                    return None
            
            # Default case if action is unknown or None
            logging.error("❌ 无效操作，将忽略此属性。")
            self.ignore_key_session(bangumi_key)
            return None
