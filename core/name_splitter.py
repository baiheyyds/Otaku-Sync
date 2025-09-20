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
    def __init__(self, interaction_provider: Optional[InteractionProvider] = None):
        self.interaction_provider = interaction_provider
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

    def _add_exception(self, name: str):
        """将新的例外添加到内存和文件中"""
        if name in self._exceptions:
            return
        self._exceptions.add(name)
        try:
            # 读取现有列表以追加，而不是覆盖
            current_exceptions = list(self._load_exceptions())
            if name not in current_exceptions:
                current_exceptions.append(name)
                with open(EXCEPTION_FILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(sorted(current_exceptions), f, ensure_ascii=False, indent=2)
                logger.success(f"已将 '{name}' 添加到例外列表，今后将自动处理。")
        except Exception as e:
            logger.error(f"自动更新例外文件失败: {e}")

    async def smart_split(self, text: str) -> List[str]:
        """
        智能分割名称字符串。
        默认使用增强的规则进行分割，仅在发现可疑结果时请求用户确认。
        """
        if not text:
            return []

        # --- [核心升级 3] 名称标准化 ---
        # 将所有内部空白（包括全角空格）统一替换为单个标准空格
        def normalize(name: str) -> str:
            return re.sub(r'\s+', ' ', name).strip()

        if text in self._exceptions:
            return [normalize(text)]

        parts = SPLIT_REGEX.split(text)
        cleaned_parts = [normalize(p) for p in parts if p.strip()]

        if len(cleaned_parts) <= 1:
            return cleaned_parts

        # --- [核心升级 2] 增强风险识别 ---
        # 规则1: 分割后出现过短的部分 (例如: 'S')
        is_dangerous = any(len(p) <= 1 for p in cleaned_parts)
        
        # 规则2: 由'・'分割的全英文名称 (例如: 'Ryo・Lion')
        is_alpha_dot_split = False
        if not is_dangerous and '・' in text and len(cleaned_parts) > 1:
            if all(re.fullmatch(r'[a-zA-Z]+', p) for p in cleaned_parts):
                is_alpha_dot_split = True
        
        if not is_dangerous and not is_alpha_dot_split:
            return cleaned_parts

        # --- Interactive part ---
        choice = "keep"  # Default action
        save_exception = False

        if self.interaction_provider:
            # TODO: 将增强的风险原因传递给GUI
            decision = await self.interaction_provider.get_name_split_decision(text, cleaned_parts)
            choice = decision.get("action", "keep")
            save_exception = decision.get("save_exception", False)
        else:
            # CLI Fallback
            def _get_input():
                logger.warn(f"检测到【高风险】的名称分割: '{text}'")
                print(f"  初步分割为: {cleaned_parts}")
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
            return cleaned_parts
        else:  # "keep"
            logger.info(f"用户选择不分割 '{text}'。")
            if save_exception:
                self._add_exception(text)
            return [normalize(text)]