# core/interaction.py
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from utils import logger

# Replicating the necessary parts from mapping_manager.py for the console implementation
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

def get_visual_width(s: str) -> int:
    return sum(2 if "\u4e00" <= char <= "\u9fff" else 1 for char in s)

class InteractionProvider(ABC):
    """Abstract base class for providing user interaction."""

    @abstractmethod
    async def handle_new_bangumi_key(
        self,
        bangumi_key: str,
        bangumi_value: Any,
        bangumi_url: str,
        db_name: str,
        mappable_props: List[str],
        recommended_props: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle a new, unmapped key from Bangumi.
        Returns a dictionary with 'action' and 'data'.
        """
        pass

    @abstractmethod
    async def get_bangumi_game_choice(self, search_term: str, candidates: List[Dict]) -> str | None:
        """Ask user to select a game from Bangumi search results."""
        pass

    @abstractmethod
    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        """Ask user to select a type for a new Notion property."""
        pass


class ConsoleInteractionProvider(InteractionProvider):
    """Console implementation for user interaction using input()."""

    async def handle_new_bangumi_key(
        self,
        bangumi_key: str,
        bangumi_value: Any,
        bangumi_url: str,
        db_name: str,
        mappable_props: List[str],
        recommended_props: List[str] = None,
    ) -> Dict[str, Any]:
        
        def _get_action_input():
            prompt_header = (
                f"\n❓ [Bangumi] 在【{db_name}】中发现新属性:\n"
                f"   - 键 (Key)  : '{bangumi_key}'\n"
                f"   - 值 (Value): {bangumi_value}\n"
                f"   - 来源 (URL) : {bangumi_url}\n\n"
                f"   请选择如何处理:\n"
            )

            recommend_lines, recommend_map = [], {}
            if recommended_props:
                recommend_lines.append("   --- 推荐映射 ---")
                rec_parts = []
                for i, prop_name in enumerate(recommended_props):
                    shortcut = chr(ord('a') + i)
                    recommend_map[shortcut] = prop_name
                    rec_parts.append(f"[{shortcut}] {prop_name}")
                recommend_lines.append("   " + "   ".join(rec_parts))

            prop_lines, prop_map = [], {}
            prop_lines.append("\n   --- 映射到现有 Notion 属性 ---")
            COLUMNS, COLUMN_WIDTH = 6, 25

            for i in range(0, len(mappable_props), COLUMNS):
                line_parts = []
                for j in range(COLUMNS):
                    if (idx := i + j) < len(mappable_props):
                        prop_name = mappable_props[idx]
                        prop_map[str(idx + 1)] = prop_name
                        display_text = f"[{idx + 1}] {prop_name}"
                        padding = " " * max(0, COLUMN_WIDTH - get_visual_width(display_text))
                        line_parts.append(display_text + padding)
                prop_lines.append("   " + "".join(line_parts))
            
            prompt_body = "\n".join(recommend_lines + prop_lines)
            prompt_footer = (
                f"\n\n   --- 或执行其他操作 ---"
                f"     [y] 在 Notion 中创建同名新属性 '{bangumi_key}' (默认)"
                f"     [n] 本次运行中忽略此属性"
                f"     [p] 永久忽略此属性 (例如 '开发', '发行' 等)"
                f"     [c] 自定义新属性名称并创建\n\n"
                f"请输入您的选择 (数字或字母): "
            )
            return input(prompt_header + prompt_body + prompt_footer).strip().lower(), prop_map, recommend_map

        action, prop_map, recommend_map = await asyncio.to_thread(_get_action_input)

        if action.isdigit() and action in prop_map:
            selected_prop = prop_map[action]
            return {"action": "map", "data": selected_prop}
        
        if action.isalpha() and action in recommend_map:
            selected_prop = recommend_map[action]
            return {"action": "map", "data": selected_prop}

        if action == "n":
            return {"action": "ignore_session"}

        if action == "p":
            return {"action": "ignore_permanent"}

        if action in {"", "y"}:
            return {"action": "create_same_name"}

        if action == "c":
            custom_name = (await asyncio.to_thread(input, "请输入要创建的自定义 Notion 属性名: ")).strip()
            if custom_name:
                return {"action": "create_custom_name", "data": custom_name}
            else:
                logger.warn("未输入名称，已取消操作。")
                return {"action": "ignore_session"}
        
        logger.error("输入无效，将忽略此属性。")
        return {"action": "ignore_session"}

    async def get_bangumi_game_choice(self, search_term: str, candidates: List[Dict]) -> str | None:
        if not candidates:
            return None

        logger.info(f'请为 "{search_term}" 选择最匹配的 Bangumi 条目:')
        for candidate in candidates:
            print(f"  {candidate['display']}")
        print("")  # Add a newline for better formatting

        try:
            raw_choice = await asyncio.to_thread(input, "请输入序号选择 Bangumi 条目（0 放弃）：")
            choice = int(raw_choice.strip())

            if choice == 0:
                logger.info("用户放弃选择。")
                return None
            
            if 1 <= choice <= len(candidates):
                # User enters 1-based index, convert to 0-based
                selected_candidate = candidates[choice - 1]
                return selected_candidate['id']
            else:
                logger.error("无效的序号，操作已取消。")
                return None
        except (ValueError, IndexError):
            logger.error("无效输入，请输入数字。操作已取消。")
            return None

    async def ask_for_new_property_type(self, prop_name: str) -> str | None:
        def _get_type_input():
            type_prompt = f"   请为新属性 '{prop_name}' 选择 Notion 中的类型:\n"
            for key, (api_type, display_name) in TYPE_SELECTION_MAP.items():
                default_str = " (默认)" if api_type == "rich_text" else ""
                type_prompt += f"     [{key}] {display_name}{default_str}\n"
            type_prompt += "     [c] 取消创建\n"
            return input(type_prompt + "   请输入选项: ").strip().lower()

        while True:
            type_choice = await asyncio.to_thread(_get_type_input)
            if type_choice == "c":
                return None
            selected_type = TYPE_SELECTION_MAP.get(type_choice or "1")
            if selected_type:
                notion_type, _ = selected_type
                return notion_type
            else:
                logger.error("无效的类型选项，请重新输入。")

# This will be implemented in a separate file to avoid circular dependencies with GUI components
# class GuiInteractionProvider(InteractionProvider):
#     ... 
