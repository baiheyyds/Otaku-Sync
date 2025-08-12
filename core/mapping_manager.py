# core/mapping_manager.py
import asyncio
import json
import os
import re
from typing import Dict, List

from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID
from utils import logger

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
                    self._mapping = json.loads(content) if content else {}
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
        return None if bangumi_key in self._ignored_keys else self._reverse_mapping.get(bangumi_key)

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
        # --- 核心修复：修正日志输出，确保映射关系清晰无误 ---
        logger.success(f"已更新映射表: Bangumi 属性 '{bangumi_key}' -> Notion 属性 '{notion_prop}'")

    def ignore_key_session(self, bangumi_key: str):
        self._ignored_keys.add(bangumi_key)
        logger.info(f"属性 '{bangumi_key}' 将在本次运行中被忽略。")

    async def _create_and_map_new_property(
        self,
        new_prop_name: str,
        bangumi_key_to_map: str,
        notion_client,
        schema_manager,
        target_db_id: str,
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
            db_name = "未知数据库"
            if target_db_id == GAME_DB_ID:
                db_name = "游戏数据库"
            elif target_db_id == BRAND_DB_ID:
                db_name = "厂商数据库"
            elif target_db_id == CHARACTER_DB_ID:
                db_name = "角色数据库"

            await schema_manager.initialize_schema(target_db_id, db_name)
            self.add_new_mapping(bangumi_key_to_map, new_prop_name)
            return new_prop_name
        else:
            logger.error(f"自动创建 Notion 属性 '{new_prop_name}' 失败，将跳过此属性。")
            return None

    async def handle_new_key(
        self, bangumi_key: str, notion_client, schema_manager, target_db_id: str
    ) -> str | None:
        db_name = "未知数据库"
        if target_db_id == GAME_DB_ID:
            db_name = "游戏数据库"
        elif target_db_id == BRAND_DB_ID:
            db_name = "厂商数据库"
        elif target_db_id == CHARACTER_DB_ID:
            db_name = "角色数据库"

        def _get_action_input():
            mappable_props = schema_manager.get_mappable_properties(target_db_id)
            prompt_header = f"\n❓ [Bangumi] 在【{db_name}】中发现新属性: '{bangumi_key}'\n   请选择如何处理:\n\n   --- 映射到现有 Notion 属性 ---\n"
            prop_lines, prop_map = [], {}
            COLUMNS, COLUMN_WIDTH = 3, 25

            def get_visual_width(s: str) -> int:
                width = 0
                for char in s:
                    if (
                        "\u4e00" <= char <= "\u9fff"
                        or "\u3040" <= char <= "\u30ff"
                        or "\uff01" <= char <= "\uff5e"
                    ):
                        width += 2
                    else:
                        width += 1
                return width

            for i in range(0, len(mappable_props), COLUMNS):
                line_parts = []
                for j in range(COLUMNS):
                    idx = i + j
                    if idx < len(mappable_props):
                        prop_name = mappable_props[idx]
                        prop_map[str(idx + 1)] = prop_name
                        display_text = f"[{idx + 1}] {prop_name}"
                        padding = " " * max(0, COLUMN_WIDTH - get_visual_width(display_text))
                        line_parts.append(display_text + padding)
                prop_lines.append("   " + "".join(line_parts))
            prompt_body = "\n".join(prop_lines)
            prompt_footer = f"\n\n   --- 或执行其他操作 ---\n     [y] 在 Notion 中创建同名新属性 '{bangumi_key}' (默认)\n     [n] 本次运行中忽略此属性\n     [c] 自定义新属性名称并创建\n\n请输入您的选择 (数字或字母): "
            choice = input(prompt_header + prompt_body + prompt_footer).strip().lower()
            return choice, prop_map

        action, prop_map = await asyncio.to_thread(_get_action_input)

        if action.isdigit() and action in prop_map:
            selected_prop = prop_map[action]
            logger.info(f"已选择映射到现有属性: '{selected_prop}'")
            self.add_new_mapping(bangumi_key, selected_prop)
            return selected_prop
        if action == "n":
            self.ignore_key_session(bangumi_key)
            return None

        if action == "" or action == "y":
            return await self._create_and_map_new_property(
                bangumi_key, bangumi_key, notion_client, schema_manager, target_db_id
            )

        if action == "c":
            custom_name = await asyncio.to_thread(input, "请输入要创建的自定义 Notion 属性名: ")
            if custom_name:
                # --- 核心修复：交换这里的参数顺序！ ---
                # 第一个参数是要在 Notion 创建的属性名 (你的输入)
                # 第二个参数是要被映射的 Bangumi 键名 (原始键)
                return await self._create_and_map_new_property(
                    custom_name.strip(), bangumi_key, notion_client, schema_manager, target_db_id
                )
            else:
                logger.warn("未输入名称，已取消操作。")
                return None

        logger.error("输入无效，请在提供的选项中选择。")
        return await self.handle_new_key(bangumi_key, notion_client, schema_manager, target_db_id)
