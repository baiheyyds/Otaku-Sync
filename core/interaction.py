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
    async def handle_new_bangumi_key(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
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
    async def confirm_brand_merge(self, new_brand_name: str, suggested_brand: str) -> str:
        """当发现一个新品牌与一个现有品牌高度相似时，询问用户如何操作。"""
        pass

    @abstractmethod
    async def select_game(self, choices: list, title: str, source: str) -> int | str | None:
        """
        要求用户从搜索结果列表中选择一个游戏。
        也处理特定于源的选项，如“切换到Fanza搜索”。
        返回选择的索引、特殊操作字符串或None。
        """
        pass

    @abstractmethod
    async def confirm_duplicate(self, candidates: list) -> str | None:
        """
        显示潜在的重复游戏，并询问用户是跳过、更新还是强制创建。
        返回 'skip', 'update', 'create' 或 None。
        """
        pass


class ConsoleInteractionProvider(InteractionProvider):
    """Console implementation for user interaction using input()."""

    async def handle_new_bangumi_key(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        bangumi_key = request_data["bangumi_key"]
        bangumi_value = request_data["bangumi_value"]
        bangumi_url = request_data["bangumi_url"]
        db_name = request_data["db_name"]
        mappable_props = request_data["mappable_props"]
        recommended_props = request_data.get("recommended_props", [])
        
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

    async def confirm_brand_merge(self, new_brand_name: str, suggested_brand: str) -> str:
        """当发现一个新品牌与一个现有品牌高度相似时，询问用户如何操作。"""
        def _get_input():
            logger.warn(f"品牌查重：检测到新品牌 ‘{new_brand_name}’ 与现有品牌 ‘{suggested_brand}’ 高度相似。")
            print("  请选择操作：")
            print(f"  [m] 合并为 ‘{suggested_brand}’ (默认)")
            print(f"  [c] 强制创建为新品牌 ‘{new_brand_name}’")
            print("  [a] 取消本次操作")
            return input("请输入您的选择 (m/c/a): ").strip().lower()

        while True:
            choice = await asyncio.to_thread(_get_input)
            if choice in {"", "m"}:
                return "merge"
            elif choice == "c":
                return "create"
            elif choice == "a":
                return "cancel"
            else:
                logger.error("输入无效，请重新输入。")

    async def get_tag_translation(self, tag: str, source_name: str) -> str:
        return (await asyncio.to_thread(input, f"- 新标签({source_name}): 请输入 ‘{tag}’ 的中文翻译 (s跳过): ")).strip()

    async def get_concept_merge_decision(self, concept: str, candidate: str) -> str | None:
        def _get_input():
            logger.warn(f"标签概念 ‘{concept}’ 与现有标签 ‘{candidate}’ 高度相似。是否合并？")
            return input("  [y] 合并 (默认) / [n] 创建为新标签 / [c] 取消: ").strip().lower()
        
        choice = await asyncio.to_thread(_get_input)
        if choice in {"", "y"}:
            return "merge"
        elif choice == "n":
            return "create"
        else:
            return None

    async def get_name_split_decision(self, text: str, parts: list) -> dict:
        def _get_input():
            logger.warn(f"名称 ‘{text}’ 被分割为: {parts}")
            print("  [k] 保持原样 (默认)")
            print("  [s] 保存为特例，以后不再分割")
            return input("请选择或按回车确认: ").strip().lower()
        
        choice = await asyncio.to_thread(_get_input)
        if choice == "s":
            return {"action": "keep", "save_exception": True}
        return {"action": "keep", "save_exception": False}

    async def select_game(self, choices: list, title: str, source: str) -> int | str | None:
        """要求用户从搜索结果列表中选择一个游戏。"""
        def _get_input():
            logger.info(title)
            if source == 'ggbases':
                for i, item in enumerate(choices):
                    size_info = item.get('容量', '未知')
                    popularity = item.get('popularity', 0)
                    print(f"  [{i+1}] {item.get('title', 'No Title')} (热度: {popularity}) (大小: {size_info})")
            else:
                for i, item in enumerate(choices):
                    price = item.get("价格") or item.get("price", "未知")
                    price_display = f"{price}円" if str(price).isdigit() else price
                    item_type = item.get("类型", "未知")
                    print(f"  [{i+1}] [{source.upper()}] {item.get('title', 'No Title')} | 💴 {price_display} | 🏷️ {item_type}")
            
            prompt = "\n请输入序号进行选择 (0 放弃"
            if source == 'dlsite':
                prompt += ", f 切换到Fanza搜索"
            prompt += "): "
            return input(prompt).strip().lower()

        while True:
            choice = await asyncio.to_thread(_get_input)
            if choice == 'f' and source == 'dlsite':
                logger.info("切换到 Fanza 搜索...")
                return "search_fanza"
            if choice == '0':
                logger.info("用户取消了选择。")
                return -1
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(choices):
                    return choice_idx
                else:
                    logger.error("无效的序号，请重新输入。")
            except ValueError:
                logger.error("无效输入，请输入数字或指定字母。")

    async def confirm_duplicate(self, candidates: list) -> str | None:
        """显示潜在的重复游戏，并询问用户如何处理。"""
        def _get_input():
            logger.warn("发现可能重复的游戏，请选择操作：")
            for i, (game, similarity) in enumerate(candidates):
                title = game.get("title", "未知标题")
                print(f"  - 相似条目: {title} (相似度: {similarity:.2f})")
            
            print("\n  [s] 跳过，不处理此游戏 (默认)")
            print("  [u] 更新最相似的已有条目")
            print("  [c] 强制创建为新条目")
            return input("请输入您的选择 (s/u/c): ").strip().lower()

        while True:
            choice = await asyncio.to_thread(_get_input)
            if choice in {'s', ''}:
                return "skip"
            elif choice == 'u':
                return "update"
            elif choice == 'c':
                return "create"
            else:
                logger.error("无效输入，请重新选择。")

# This will be implemented in a separate file to avoid circular dependencies with GUI components
# class GuiInteractionProvider(InteractionProvider):
#     ... 
