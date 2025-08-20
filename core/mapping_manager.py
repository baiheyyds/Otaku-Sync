# core/mapping_manager.py
import asyncio
import json
import os
from typing import Dict, List

from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID
from utils import logger

MAPPING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mapping")
BGM_PROP_MAPPING_PATH = os.path.join(MAPPING_DIR, "bangumi_prop_mapping.json")
# --- [新增 1] 定义永久忽略列表的文件路径 ---
BGM_IGNORE_LIST_PATH = os.path.join(MAPPING_DIR, "bangumi_ignore_list.json")


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

DB_ID_TO_NAMESPACE = {
    GAME_DB_ID: "games",
    CHARACTER_DB_ID: "characters",
    BRAND_DB_ID: "brands",
}


class BangumiMappingManager:
    def __init__(self, file_path: str = BGM_PROP_MAPPING_PATH):
        self.file_path = file_path
        self._mapping: Dict[str, Dict[str, List[str]]] = {}
        self._reverse_mapping: Dict[str, Dict[str, str]] = {}
        self._ignored_keys: set = set()

        # --- [新增 2] 初始化永久忽略列表的变量 ---
        self._permanent_ignored_keys: set = set()
        # --- 新增结束 ---

        self._load_mapping()
        # --- [新增 3] 在初始化时加载永久忽略列表 ---
        self._load_ignore_list()
        # --- 新增结束 ---

    # --- [新增 4] 新增加载永久忽略列表的方法 ---
    def _load_ignore_list(self):
        """从文件加载永久忽略的 Bangumi 属性键。"""
        if not os.path.exists(BGM_IGNORE_LIST_PATH):
            self._permanent_ignored_keys = set()
            return
        try:
            with open(BGM_IGNORE_LIST_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                # 确保文件内容不为空
                ignore_list = json.loads(content) if content else []
                self._permanent_ignored_keys = set(ignore_list)
                logger.system(
                    f"已加载 {len(self._permanent_ignored_keys)} 个永久忽略的 Bangumi 属性。"
                )
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载 Bangumi 忽略列表文件失败: {e}")
            self._permanent_ignored_keys = set()

    # --- 新增结束 ---

    def _load_mapping(self):
        default_structure = {"games": {}, "characters": {}, "brands": {}}
        if not os.path.exists(self.file_path):
            self._mapping = default_structure
        else:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    loaded_mapping = json.loads(content) if content else {}
                    self._mapping = {**default_structure, **loaded_mapping}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载 Bangumi 映射文件失败: {e}")
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
        # 检查是否在忽略列表中
        if self.is_ignored(bangumi_key):
            return None
        namespace = DB_ID_TO_NAMESPACE.get(db_id)
        if not namespace:
            return None
        return self._reverse_mapping.get(namespace, {}).get(bangumi_key)

    # --- [新增 5] 新增检查是否在忽略列表中的方法 ---
    def is_ignored(self, bangumi_key: str) -> bool:
        """Checks if a key is in either the session or permanent ignore list."""
        return bangumi_key in self._ignored_keys or bangumi_key in self._permanent_ignored_keys
    

    def add_new_mapping(self, bangumi_key: str, notion_prop: str, db_id: str):
        namespace = DB_ID_TO_NAMESPACE.get(db_id)
        if not namespace:
            logger.error(f"未知的数据库ID {db_id}，无法添加映射。")
            return

        namespace_mappings = self._mapping.setdefault(namespace, {})
        key_list = namespace_mappings.setdefault(notion_prop, [])
        if bangumi_key not in key_list:
            key_list.append(bangumi_key)

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
        except IOError as e:
            logger.error(f"保存 Bangumi 映射文件失败: {e}")
            return

        self._reverse_mapping.setdefault(namespace, {})[bangumi_key] = notion_prop
        logger.success(
            f"已更新【{namespace}】映射表: Bangumi '{bangumi_key}' -> Notion '{notion_prop}'"
        )

    def ignore_key_session(self, bangumi_key: str):
        self._ignored_keys.add(bangumi_key)
        logger.info(f"属性 '{bangumi_key}' 将在本次运行中被忽略。")

    # --- [新增 6] 新增一个将键添加到永久忽略列表并保存的方法 ---
    def _add_to_permanent_ignore_list(self, bangumi_key: str):
        """将一个键添加到永久忽略列表并保存到文件。"""
        if bangumi_key in self._permanent_ignored_keys:
            return
        self._permanent_ignored_keys.add(bangumi_key)
        try:
            # 转换为排序后的列表以便于阅读和版本控制
            sorted_ignore_list = sorted(list(self._permanent_ignored_keys))
            with open(BGM_IGNORE_LIST_PATH, "w", encoding="utf-8") as f:
                json.dump(sorted_ignore_list, f, ensure_ascii=False, indent=2)
            logger.success(f"已将 '{bangumi_key}' 添加到永久忽略列表。")
        except IOError as e:
            logger.error(f"保存 Bangumi 永久忽略列表失败: {e}")

    # --- 新增结束 ---

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
            logger.system(f"新属性已创建，正在刷新数据库结构缓存...")
            db_name = DB_ID_TO_NAMESPACE.get(target_db_id, "未知数据库")
            await schema_manager.initialize_schema(target_db_id, db_name)
            self.add_new_mapping(bangumi_key_to_map, new_prop_name, target_db_id)
            return new_prop_name
        else:
            logger.error(f"自动创建 Notion 属性 '{new_prop_name}' 失败。")
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
        db_name = "未知数据库"
        namespace = DB_ID_TO_NAMESPACE.get(target_db_id)
        if namespace == "games":
            db_name = "游戏数据库"
        elif namespace == "characters":
            db_name = "角色数据库"
        elif namespace == "brands":
            db_name = "厂商数据库"

        def _get_action_input():
            mappable_props = schema_manager.get_mappable_properties(target_db_id)
            prompt_header = (
                f"\n❓ [Bangumi] 在【{db_name}】中发现新属性:\n"
                f"   - 键 (Key)  : '{bangumi_key}'\n"
                f"   - 值 (Value): {bangumi_value}\n"
                f"   - 来源 (URL) : {bangumi_url}\n\n"
                f"   请选择如何处理:\n\n   --- 映射到现有 Notion 属性 ---\n"
            )
            prop_lines, prop_map = [], {}
            COLUMNS, COLUMN_WIDTH = 6, 25

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

            prompt_footer = (
                f"\n\n   --- 或执行其他操作 ---\n"
                f"     [y] 在 Notion 中创建同名新属性 '{bangumi_key}' (默认)\n"
                f"     [n] 本次运行中忽略此属性\n"
                f"     [p] 永久忽略此属性 (例如 '开发', '发行' 等)\n"
                f"     [c] 自定义新属性名称并创建\n\n"
                f"请输入您的选择 (数字或字母): "
            )

            choice = input(prompt_header + prompt_body + prompt_footer).strip().lower()
            return choice, prop_map

        action, prop_map = await asyncio.to_thread(_get_action_input)

        if action.isdigit() and action in prop_map:
            selected_prop = prop_map[action]
            logger.info(f"已选择映射到现有属性: '{selected_prop}'")
            self.add_new_mapping(bangumi_key, selected_prop, target_db_id)
            return selected_prop

        if action == "n":
            self.ignore_key_session(bangumi_key)
            return None

        # --- [核心修复：补上遗漏的逻辑块] ---
        if action == "p":
            self._add_to_permanent_ignore_list(bangumi_key)
            return None  # 忽略后直接返回，不再处理
        # --- [修复结束] ---

        if action == "" or action == "y":
            return await self._create_and_map_new_property(
                bangumi_key, bangumi_key, notion_client, schema_manager, target_db_id
            )

        if action == "c":
            custom_name = await asyncio.to_thread(input, "请输入要创建的自定义 Notion 属性名: ")
            if custom_name:
                return await self._create_and_map_new_property(
                    custom_name.strip(), bangumi_key, notion_client, schema_manager, target_db_id
                )
            else:
                logger.warn("未输入名称，已取消操作。")
                return None

        logger.error("输入无效，请在提供的选项中选择。")
        return await self.handle_new_key(
            bangumi_key, bangumi_value, bangumi_url, notion_client, schema_manager, target_db_id
        )
