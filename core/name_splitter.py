# core/name_splitter.py
import asyncio
import json
import os
import re
from typing import List, Set, Optional

from utils import logger
from core.interaction import InteractionProvider

EXCEPTION_FILE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "mapping", "name_split_exceptions.json"
)

# --- [核心升级 1] 使用更强大的正则表达式 ---
# 涵盖了：、・,／/ ; 但不包括作为分隔符的空白符
SPLIT_REGEX = re.compile(r"[、・,／/;]+")


class NameSplitter:
    def __init__(self):
        self._exceptions: Set[str] = self._load_exceptions()

    def _load_exceptions(self) -> Set[str]:
        """加载名称分割的例外列表"""
        try:
            if os.path.exists(EXCEPTION_FILE_PATH):
                with open(EXCEPTION_FILE_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                    return set(json.loads(content)) if content else set()
        except (json.JSONDecodeError, IOError) as e:
            logger.warn(f"加载名称分割例外文件失败: {e}")
        return set()

    def save_exceptions(self):
        """将内存中的例外列表保存到文件。"""
        if not self._exceptions:
            return
        logger.system("正在保存名称分割例外列表...")
        try:
            with open(EXCEPTION_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self._exceptions)), f, ensure_ascii=False, indent=2)
            logger.success("名称分割例外列表已保存。")
        except Exception as e:
            logger.error(f"保存名称分割例外文件失败: {e}")

    def _add_exception(self, name: str):
        """将新的例外添加到内存中。"""
        if name in self._exceptions:
            return
        self._exceptions.add(name)
        logger.info(f"已在内存中将 '{name}' 标记为本次运行的例外。")

    def _post_process_parts(self, parts: List[str]) -> List[str]:
        """
        对分割后的部分进行后处理，自动合并 "J・さいろー" 或 "神・无月" 这样的模式。
        """
        if len(parts) < 2:
            return parts

        new_parts = []
        i = 0
        while i < len(parts):
            current_part = parts[i]
            # --- 核心改进：检查是否为任意类型的单个字符 ---
            if len(current_part) == 1:
                # 如果后面还有部分，则合并
                if i + 1 < len(parts):
                    next_part = parts[i+1]
                    merged_part = f"{current_part}・{next_part}"
                    new_parts.append(merged_part)
                    i += 2  # 跳过下一个部分，因为它已经被合并
                else:
                    # 这是最后一部分，无法合并，照常添加
                    new_parts.append(current_part)
                    i += 1
            else:
                new_parts.append(current_part)
                i += 1
        return new_parts

    async def smart_split(self, text: str, interaction_provider: InteractionProvider) -> List[str]:
        """
        智能分割名称字符串。
        默认使用增强的规则进行分割，仅在发现可疑结果时请求用户确认。
        """
        if not text:
            return []

        def normalize(name: str) -> str:
            return re.sub(r'\s+', ' ', name).strip()

        if text in self._exceptions:
            return [normalize(text)]

        parts = SPLIT_REGEX.split(text)
        cleaned_parts = [normalize(p) for p in parts if p.strip()]

        # --- [核心升级 2] 启发式识别：处理 '名字A・名字B' 模式 ---
        # 如果分割结果为三部分，且中间部分为单个字符，则极有可能是完整的姓名
        if len(cleaned_parts) == 3 and len(cleaned_parts[1]) == 1 and (len(cleaned_parts[0]) > 1 or len(cleaned_parts[2]) > 1):
            logger.info(f"检测到 '名字・首字母・名字' 模式，自动合并: {text}")
            return [normalize(text)]

        # 在风险识别前，先进行智能后处理
        processed_parts = self._post_process_parts(cleaned_parts)

        if len(processed_parts) <= 1:
            return processed_parts

        # 增强风险识别 (现在基于后处理的结果)
        is_dangerous = any(len(p) <= 1 for p in processed_parts)
        
        is_alpha_dot_split = False
        if not is_dangerous and '・' in text and len(processed_parts) > 1:
            if all(re.fullmatch(r'[a-zA-Z]+', p) for p in processed_parts):
                is_alpha_dot_split = True
        
        if not is_dangerous and not is_alpha_dot_split:
            return processed_parts

        # --- Interactive part ---
        choice = "keep"
        save_exception = False

        if interaction_provider:
            decision = await interaction_provider.get_name_split_decision(text, processed_parts)
            choice = decision.get("action", "keep")
            save_exception = decision.get("save_exception", False)
        else:
            # CLI Fallback
            def _get_input():
                logger.warn(f"检测到【高风险】的名称分割: '{text}'")
                print(f"  初步分割为: {processed_parts}")
                if is_alpha_dot_split:
                    print("  原因: 检测到由'・'分割的纯英文名称，这可能是一个完整的名字。")
                else:
                    print("  原因: 检测到分割后有极短的部分 (如单个字母)，可能分割错误。")
                print("  请选择如何处理:")
                print("    [1] 这是一个完整的名字，不要分割 (例如 'Ryo・Lion') (默认)")
                print("    [2] 以上分割是正确的 (例如 'A・B')")
                return input("  请输入你的选择 (1/2): ").strip()

            cli_choice = await asyncio.to_thread(_get_input)
            if cli_choice == "2":
                choice = "split"
            else:
                choice = "keep"
            
            if choice == "keep":
                def _get_save_confirmation():
                    return (
                        input(f"  是否将 '{text}' 添加到例外列表，以便今后自动处理? (y/N): ")
                        .strip()
                        .lower()
                    )
                save_choice = await asyncio.to_thread(_get_save_confirmation)
                if save_choice == "y":
                    save_exception = True

        # --- Process decision ---
        if choice == "split":
            return processed_parts
        else:  # "keep"
            logger.info(f"用户选择不分割 '{text}'。")
            if save_exception:
                self._add_exception(text)
            return [normalize(text)]