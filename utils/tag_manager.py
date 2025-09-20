# utils/tag_manager.py
import asyncio
import json
import os
from typing import Dict, List, Set, Optional

from utils import logger
from core.interaction import InteractionProvider

# --- 文件路径定义 ---
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
                elif isinstance(data, list):
                    sorted_data = sorted(data)
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存映射文件失败 {os.path.basename(path)}: {e}")

    def save_all_maps(self):
        """将所有内存中的映射关系保存到对应的JSON文件中。"""
        logger.system("正在保存所有标签映射文件...")
        self._save_map(TAG_JP_TO_CN_PATH, self._jp_to_cn_map)
        self._save_map(TAG_FANZA_TO_CN_PATH, self._fanza_to_cn_map)
        self._save_map(TAG_GGBASE_PATH, self._ggbase_map)
        self._save_map(TAG_IGNORE_PATH, list(self._ignore_set))
        self._save_map(TAG_MAPPING_DICT_PATH, self._mapping_dict)
        logger.success("所有标签映射文件已保存。")

    def _build_unified_reverse_map(self) -> Dict[str, str]:
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

    def _find_best_merge_candidate(self, concept: str) -> Optional[str]:
        if candidate := self._unified_reverse_map.get(concept.lower()):
            return candidate
        unique_known_concepts = set(self._unified_reverse_map.values())
        component_matches = []
        for known_concept in unique_known_concepts:
            parts = [p.strip() for p in known_concept.split("/")]
            if concept in parts:
                component_matches.append(known_concept)
        if component_matches:
            return min(component_matches, key=len)
        substring_matches = []
        for known_concept in unique_known_concepts:
            if concept in known_concept:
                substring_matches.append(known_concept)
        if substring_matches:
            return min(substring_matches, key=len)
        return None

    async def _get_translation_interactively(
        self, tag: str, source_map: dict, map_path: str, source_name: str, interaction_provider: InteractionProvider
    ) -> str | None:
        if interaction_provider:
            translation = await interaction_provider.get_tag_translation(tag, source_name)
        else:
            def get_input():
                logger.warn(f"发现新的【{source_name}】标签: '{tag}'")
                print("  > 请输入对应的中文翻译。")
                print("  > 输入 's' 跳过本次，'p' 永久忽略此标签。")
                return input(f"  翻译为: ").strip()
            translation = await asyncio.to_thread(get_input)

        if translation is None or translation.lower() == "s":
            logger.info(f"已跳过标签 '{tag}'。")
            return None
        if translation.lower() == "p":
            self._ignore_set.add(tag)
            logger.info(f"标签 '{tag}' 已被标记为永久忽略。")
            return None
        if not translation:
            logger.warn("输入为空，已跳过。")
            return None
        
        source_map[tag] = translation
        logger.success(f"已在内存中添加新翻译: '{tag}' -> '{translation}'")
        return translation

    async def _handle_new_concept_interactively(self, concept: str, interaction_provider: InteractionProvider) -> str:
        candidate = self._find_best_merge_candidate(concept)
        final_concept = concept

        if candidate and candidate != concept:
            if interaction_provider:
                choice = await interaction_provider.get_concept_merge_choice(concept, candidate)
            else:
                def get_choice():
                    logger.system(f"新的中文概念 '{concept}' 与已有的标签组 '{candidate}' 高度相关。")
                    print(f"  是否要将 '{concept}' 合并到 '{candidate}' 组中？")
                    print(f"    1. 【合并】(推荐)")
                    print(f"    2. 【创建】将 '{concept}' 作为独立标签")
                    return input("  请选择 [1]: ").strip()
                choice = await asyncio.to_thread(get_choice)

            if choice in [None, "", "1", "merge"]:
                keywords = self._mapping_dict.get(candidate, [candidate])
                new_keywords = set(keywords)
                new_keywords.add(concept)
                self._mapping_dict[candidate] = sorted(list(new_keywords))
                logger.success(f"操作成功！已在内存中将概念 '{concept}' 合并到 '{candidate}'。")
                final_concept = candidate
            elif choice in ["2", "create"]:
                if concept not in self._mapping_dict:
                    self._mapping_dict[concept] = [concept]
                logger.info(f"已在内存中将 '{concept}' 创建为新的独立标签。")
        
        self._unified_reverse_map[concept.lower()] = final_concept
        if final_concept.lower() not in self._unified_reverse_map:
             self._unified_reverse_map[final_concept.lower()] = final_concept

        return final_concept

    async def process_tags(
        self,
        dlsite_tags: List[str],
        fanza_tags: List[str],
        ggbases_tags: List[str],
        interaction_provider: InteractionProvider,
    ) -> List[str]:
        async with self._interaction_lock:
            translated_tags = []
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
                            tag, source_map, map_path, source_name, interaction_provider
                        )
                    if translation:
                        translated_tags.append(translation)

            for tag in ggbases_tags:
                translated = self._ggbase_map.get(tag, tag) or tag
                if translated:
                    translated_tags.append(translated)

            final_tags_set: Set[str] = set()
            for concept in list(dict.fromkeys(translated_tags)):
                concept = concept.strip()
                if not concept:
                    continue

                main_tag = self._unified_reverse_map.get(concept.lower())

                if not main_tag:
                    main_tag = await self._handle_new_concept_interactively(concept, interaction_provider)
                
                final_tags_set.add(main_tag)

            return sorted(list(final_tags_set))