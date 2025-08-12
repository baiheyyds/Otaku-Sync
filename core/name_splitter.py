# core/name_splitter.py
import asyncio
import json
import os
import re
from typing import List, Set

from utils import logger

EXCEPTION_FILE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "mapping", "name_split_exceptions.json"
)
# 定义用于分割的正则表达式
SPLIT_REGEX = re.compile(r"[、・, ]+")
# 定义用于检测危险情况的正则表达式 (与分割正则相同)
DANGER_CHECK_REGEX = re.compile(r"[、・, ]")


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

    def _add_exception(self, name: str):
        """将新的例外添加到内存和文件中"""
        self._exceptions.add(name)
        try:
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
        智能分割名称字符串。默认分割是正确的，只在极特殊情况下请求用户输入。
        """
        if not text:
            return []

        # 1. 检查是否是已知的例外情况
        if text in self._exceptions:
            return [text]

        # 2. 正常分割
        parts = SPLIT_REGEX.split(text)
        cleaned_parts = [p.strip() for p in parts if p.strip()]

        # 3. 如果分割后只有一个部分，说明没有分隔符，直接返回
        if len(cleaned_parts) <= 1:
            return cleaned_parts

        # 4. 智能检测危险情况：分割后的某个部分是否仍然包含分隔符？
        #    例如 "A・B、C" 会被分割为 ["A", "B", "C"]，这没有问题。
        #    但如果一个名字是 "Team A・B"，而我们只按逗号分割，可能会得到 ["Team A・B"]，
        #    这时就需要进一步检查。
        #    (当前设计下，我们的正则已经很全面，这种情况很少发生，但作为保险)
        is_dangerous = any(DANGER_CHECK_REGEX.search(p) for p in cleaned_parts)

        # 5. --- 核心逻辑修改 ---
        # 默认分割是正确的，只有在检测到危险情况时才请求确认
        if not is_dangerous:
            return cleaned_parts

        # --- 只有在极少数危险情况下，才会执行以下交互代码 ---

        def _get_input():
            logger.warn(f"检测到【高度歧义】的名称: '{text}'")
            print("  它将被分割为:", cleaned_parts)
            print("  请选择如何处理:")
            print("    [1] 这是一个完整的名字，不要分割 (默认)")
            print("    [2] 以上分割是正确的")
            return input("  请输入你的选择 (1/2): ").strip()

        choice = await asyncio.to_thread(_get_input)

        if choice == "2":
            # 用户确认分割是正确的
            return cleaned_parts
        else:
            # 用户选择不分割 (默认)
            def _get_save_confirmation():
                return (
                    input(f"  是否将 '{text}' 添加到例外列表，以便今后自动处理? (y/N): ")
                    .strip()
                    .lower()
                )

            save_choice = await asyncio.to_thread(_get_save_confirmation)
            if save_choice == "y":
                self._add_exception(text)

            return [text]


# 创建一个全局实例，方便其他模块直接导入使用
name_splitter = NameSplitter()
