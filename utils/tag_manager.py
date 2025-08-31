# utils/tag_manager.py
import asyncio
import json
import os
from typing import Dict, List, Set, Optional

from utils import logger

# --- 文件路径定义 (无变化) ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING_DIR = os.path.join(BASE_DIR, "mapping")
TAG_JP_TO_CN_PATH = os.path.join(MAPPING_DIR, "tag_jp_to_cn.json")
TAG_FANZA_TO_CN_PATH = os.path.join(MAPPING_DIR, "tag_fanza_to_cn.json")
TAG_GGBASE_PATH = os.path.join(MAPPING_DIR, "tag_ggbase.json")
TAG_IGNORE_PATH = os.path.join(MAPPING_DIR, "tag_ignore_list.json")
TAG_MAPPING_DICT_PATH = os.path.join(MAPPING_DIR, "tag_mapping_dict.json")


class TagManager:
    """一个用于交互式处理、翻译和映射标签的中央管理器。"""

    def __init__(self):
        self._interaction_lock = asyncio.Lock()
        self._jp_to_cn_map = self._load_map(TAG_JP_TO_CN_PATH)
        self._fanza_to_cn_map = self._load_map(TAG_FANZA_TO_CN_PATH)
        self._ggbase_map = self._load_map(TAG_GGBASE_PATH)
        self._ignore_set = set(self._load_map(TAG_IGNORE_PATH, default_type=list))
        self._mapping_dict = self._load_map(TAG_MAPPING_DICT_PATH)
        self._unified_reverse_map = self._build_unified_reverse_map()

    # --- _load_map 和 _save_map 无变化 ---
    def _load_map(self, path: str, default_type=dict):
        if not os.path.exists(path):
            return default_type()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return json.loads(content) if content else default_type()
        except (json.JSONDecodeError, IOError):
            return default_type()

    def _save_map(self, path: str, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                sorted_data = data
                if isinstance(data, dict):
                    sorted_data = dict(sorted(data.items()))
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存映射文件失败 {os.path.basename(path)}: {e}")

    def _build_unified_reverse_map(self) -> Dict[str, str]:
        # ... 此核心方法无变化，它依然是智能检测的基础 ...
        unified_map = {}
        for main_tag, keywords in self._mapping_dict.items():
            unified_map[main_tag.strip().lower()] = main_tag
            for keyword in keywords:
                unified_map[keyword.strip().lower()] = main_tag

        all_translation_values = list(self._jp_to_cn_map.values()) + list(
            self._fanza_to_cn_map.values()
        )
        for translated_tag in all_translation_values:
            if translated_tag.strip().lower() not in unified_map:
                unified_map[translated_tag.strip().lower()] = translated_tag
        return unified_map

    # --- 【重构】第一步：只负责翻译的函数 ---
    async def _get_translation_interactively(
        self, tag: str, source_map: dict, map_path: str, source_name: str
    ) -> str | None:
        """只负责获取新标签的翻译，并更新源翻译文件。"""

        def get_input():
            logger.warn(f"发现新的【{source_name}】标签: '{tag}'")
            print("  > 请输入对应的中文翻译。")
            print("  > 输入 's' 跳过本次，'p' 永久忽略此标签。")
            return input(f"  翻译为: ").strip()

        translation = await asyncio.to_thread(get_input)

        if translation.lower() == "s":
            logger.info(f"已跳过标签 '{tag}'。")
            return None
        if translation.lower() == "p":
            self._ignore_set.add(tag)
            self._save_map(TAG_IGNORE_PATH, sorted(list(self._ignore_set)))
            logger.success(f"已将 '{tag}' 添加到永久忽略列表。")
            return None
        if not translation:
            logger.warn("输入为空，已跳过。")
            return None

        # 保存纯粹的翻译
        source_map[tag] = translation
        self._save_map(map_path, source_map)
        logger.success(f"已添加新翻译: '{tag}' -> '{translation}'")
        return translation

    # --- 【重构】第二步：只负责合并的函数 ---
    async def _handle_new_concept_interactively(self, concept: str) -> str:
        """当遇到一个新的中文概念时，触发此函数来决定是否合并。"""
        candidate = self._unified_reverse_map.get(concept.lower())
        for known_concept in self._unified_reverse_map.values():
            if concept in known_concept:
                candidate = known_concept
                break

        if candidate and candidate != concept:

            def get_choice():
                logger.system(f"新的中文概念 '{concept}' 与已有的标签组 '{candidate}' 高度相关。")
                print(f"  是否要将 '{concept}' 合并到 '{candidate}' 组中？")
                print(f"    1. 【合并】(推荐)")
                print(f"    2. 【创建】将 '{concept}' 作为独立标签")
                return input("  请选择 [1]: ").strip()

            choice = await asyncio.to_thread(get_choice)

            if choice in ["", "1"]:
                keywords = self._mapping_dict.get(candidate, [candidate])
                new_keywords = set(keywords)
                new_keywords.add(concept)
                self._mapping_dict[candidate] = sorted(list(new_keywords))
                self._save_map(TAG_MAPPING_DICT_PATH, self._mapping_dict)
                logger.success(f"操作成功！已将概念 '{concept}' 合并到 '{candidate}'。")
                return candidate

        # 如果没有候选项，或用户选择不合并，则返回概念本身
        return concept

    async def process_tags(
        self, dlsite_tags: List[str], fanza_tags: List[str], ggbases_tags: List[str]
    ) -> List[str]:
        """【重构】处理所有来源标签的主流程，清晰地分为翻译和合并两个阶段。"""
        async with self._interaction_lock:  # 全局锁，保证交互不冲突
            translated_tags = []

            # --- 阶段一：翻译 ---
            source_maps = [
                (dlsite_tags, self._jp_to_cn_map, TAG_JP_TO_CN_PATH, "DLsite"),
                (fanza_tags, self._fanza_to_cn_map, TAG_FANZA_TO_CN_PATH, "Fanza"),
            ]
            for tags, source_map, map_path, source_name in source_maps:
                for tag in tags:
                    if tag in self._ignore_set:
                        continue

                    translation = source_map.get(tag)
                    if not translation:
                        translation = await self._get_translation_interactively(
                            tag, source_map, map_path, source_name
                        )
                    if translation:
                        translated_tags.append(translation)

            # 添加 GGBases 标签
            for tag in ggbases_tags:
                translated = self._ggbase_map.get(tag, tag) or tag
                if translated:
                    translated_tags.append(translated)

            # --- 阶段二：合并 ---
            final_tags_set: Set[str] = set()
            for concept in translated_tags:
                concept = concept.strip()
                if not concept:
                    continue

                # 检查这个概念是否已经有合并规则
                main_tag = self._unified_reverse_map.get(concept.lower())

                if not main_tag:
                    # 如果没有，这是一个新概念，触发合并处理流程
                    main_tag = await self._handle_new_concept_interactively(concept)
                    # 处理后，实时更新知识库，为本次运行的后续标签服务
                    self._unified_reverse_map = self._build_unified_reverse_map()

                final_tags_set.add(main_tag)

            return sorted(list(final_tags_set))
