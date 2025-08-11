# core/mapping_manager.py
# 该模块用于动态管理 Bangumi 属性映射
import asyncio
import json
import os
from typing import Dict, List

# --- 核心改动：直接从配置文件导入 ID，不再依赖 NotionClient ---
from config.config_token import CHARACTER_DB_ID
from utils import logger

# --- 核心改动结束 ---

MAPPING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mapping")
BGM_PROP_MAPPING_PATH = os.path.join(MAPPING_DIR, "bangumi_prop_mapping.json")

TYPE_SELECTION_MAP = {
    "1": ("rich_text", "文本"),
    "2": ("number", "数字"),
    "3": ("select", "单选"),
    "4": ("multi_select", "多选"),
    "5": ("date", "日期"),
    "6": ("url", "网址"),
    "7": ("files", "文件"),
    "8": ("checkbox", "复选框"),
}


class BangumiMappingManager:
    def __init__(self, file_path: str = BGM_PROP_MAPPING_PATH):
        self.file_path = file_path
        self._mapping: Dict[str, List[str]] = {}
        self._reverse_mapping: Dict[str, str] = {}
        self._ignored_keys: set = set()
        self._load_mapping()

    def _load_mapping(self):
        if not os.path.exists(self.file_path):
            self._mapping = {}
        else:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content:
                        self._mapping = {}
                    else:
                        self._mapping = json.loads(content)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载 Bangumi 映射文件失败: {e}")
                self._mapping = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        self._reverse_mapping = {}
        for notion_prop, bangumi_keys in self._mapping.items():
            for key in bangumi_keys:
                self._reverse_mapping[key] = notion_prop

    def get_notion_prop(self, bangumi_key: str) -> str | None:
        if bangumi_key in self._ignored_keys:
            return None
        return self._reverse_mapping.get(bangumi_key)

    def add_new_mapping(self, bangumi_key: str, notion_prop: str):
        current_mapping_on_disk = {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    current_mapping_on_disk = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        if notion_prop in current_mapping_on_disk:
            if bangumi_key not in current_mapping_on_disk[notion_prop]:
                current_mapping_on_disk[notion_prop].append(bangumi_key)
        else:
            current_mapping_on_disk[notion_prop] = [bangumi_key]

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(current_mapping_on_disk, f, ensure_ascii=False, indent=2, sort_keys=True)
        except IOError as e:
            logger.error(f"保存 Bangumi 映射文件失败: {e}")
            return

        self._mapping = current_mapping_on_disk
        self._build_reverse_mapping()
        logger.success(f"已更新映射表: '{bangumi_key}' -> '{notion_prop}'")

    def ignore_key_session(self, bangumi_key: str):
        self._ignored_keys.add(bangumi_key)
        logger.info(f"属性 '{bangumi_key}' 将在本次运行中被忽略。")

    async def _create_and_map_new_property(
        self, bangumi_key: str, new_prop_name: str, notion_client, schema_manager, target_db_id: str
    ) -> str | None:
        def _get_type_input():
            type_prompt = f"   请为新属性 '{new_prop_name}' 选择 Notion 中的类型:\n"
            for key, (api_type, display_name) in TYPE_SELECTION_MAP.items():
                default_str = " (默认)" if api_type == "rich_text" else ""
                type_prompt += f"     [{key}] {display_name}{default_str}\n"
            type_prompt += "     [c] 取消创建\n"
            return input(type_prompt + "   请输入选项: ").strip().lower()

        while True:
            type_choice = await asyncio.to_thread(_get_type_input)
            if type_choice == "c":
                logger.info("已取消创建新属性。")
                return None

            selected_type = TYPE_SELECTION_MAP.get(type_choice or "1")
            if selected_type:
                notion_type, _ = selected_type
                break
            else:
                logger.error("无效的类型选项，请重新输入。")

        success = await notion_client.add_new_property_to_db(
            target_db_id, new_prop_name, notion_type
        )
        if success:
            # --- 核心改动：使用导入的常量进行比较 ---
            db_name = "角色数据库" if target_db_id == CHARACTER_DB_ID else "厂商数据库"
            await schema_manager.initialize_schema(target_db_id, db_name)
            self.add_new_mapping(bangumi_key, new_prop_name)
            return new_prop_name
        else:
            logger.error(f"自动创建 Notion 属性 '{new_prop_name}' 失败，将跳过此属性。")
            return None

    async def handle_new_key(
        self, bangumi_key: str, notion_client, schema_manager, target_db_id: str
    ) -> str | None:
        def _get_action_input():
            prompt = (
                f"\n❓ [Bangumi] 发现新的infobox属性: '{bangumi_key}'\n"
                f"   [y] 创建同名新属性 (默认)\n"
                f"   [n] 本次运行中忽略\n"
                f"   或输入一个【自定义的/已存在的】Notion属性名来映射\n"
                f"请输入您的选择: "
            )
            return input(prompt).strip()

        action = await asyncio.to_thread(_get_action_input)

        if action.lower() == "n":
            self.ignore_key_session(bangumi_key)
            return None

        if action == "" or action.lower() == "y":
            return await self._create_and_map_new_property(
                bangumi_key, bangumi_key, notion_client, schema_manager, target_db_id
            )

        custom_prop_name = action
        prop_type = schema_manager.get_property_type(target_db_id, custom_prop_name)

        if prop_type:
            logger.info(f"属性 '{custom_prop_name}' 已存在于 Notion 中，将直接映射。")
            self.add_new_mapping(bangumi_key, custom_prop_name)
            return custom_prop_name
        else:

            def _get_confirmation():
                confirm_prompt = (
                    f"   ⚠️ 您输入的属性 '{custom_prop_name}' 在 Notion 中不存在。\n"
                    f"   是否要立即创建它？ (y/n, 默认 y): "
                )
                return input(confirm_prompt).strip().lower()

            confirmation = await asyncio.to_thread(_get_confirmation)
            if confirmation == "" or confirmation == "y":
                return await self._create_and_map_new_property(
                    bangumi_key, custom_prop_name, notion_client, schema_manager, target_db_id
                )
            else:
                logger.info(f"已取消为 '{bangumi_key}' 创建新属性 '{custom_prop_name}'。")
                return None
