# utils/tag_manager.py
import asyncio
import json
import os
from typing import Dict, List, Set

from utils import logger

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
        self._reverse_mapping_dict = self._build_reverse_map(self._mapping_dict)

    def _load_map(self, path: str, default_type=dict):
        """安全地加载JSON文件。"""
        if not os.path.exists(path):
            return default_type()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return json.loads(content) if content else default_type()
        except (json.JSONDecodeError, IOError):
            return default_type()

    def _save_map(self, path: str, data):
        """将数据（字典或列表）保存到JSON文件。"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                # 对字典的键进行排序，使文件内容更稳定
                sorted_data = data
                if isinstance(data, dict):
                    sorted_data = dict(sorted(data.items()))
                json.dump(sorted_data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存映射文件失败 {os.path.basename(path)}: {e}")

    def _build_reverse_map(self, mapping_dict: dict) -> dict:
        """构建用于标签合并的反向映射。"""
        reverse_map = {}
        for main_tag, keywords in mapping_dict.items():
            for keyword in keywords:
                reverse_map[keyword.strip().lower()] = main_tag
        return reverse_map

    async def _handle_new_tag(
        self, tag: str, source_map: dict, map_path: str, source_name: str
    ) -> str | None:
        """处理新标签的交互式流程。"""
        async with self._interaction_lock:
            # 双重检查，防止在等待锁的过程中标签已被其他任务处理
            if tag in source_map or tag in self._ignore_set:
                return source_map.get(tag)

            def _get_input():
                logger.warn(f"发现新的【{source_name}】标签: '{tag}'")
                print("  > 请输入对应的中文翻译。")
                print("  > 输入 's' 跳过本次，'p' 永久忽略此标签。")
                return input(f"  翻译为: ").strip()

            translation = await asyncio.to_thread(_get_input)

            if translation.lower() == "s":
                logger.info(f"已跳过标签 '{tag}'。")
                return None
            elif translation.lower() == "p":
                self._ignore_set.add(tag)
                self._save_map(TAG_IGNORE_PATH, sorted(list(self._ignore_set)))
                logger.success(f"已将 '{tag}' 添加到永久忽略列表。")
                return None
            elif translation:
                source_map[tag] = translation
                self._save_map(map_path, source_map)
                logger.success(f"已添加新映射: '{tag}' -> '{translation}'")
                return translation
            else:
                logger.warn("输入为空，已跳过。")
                return None

    async def process_tags(
        self, dlsite_tags: List[str], fanza_tags: List[str], ggbases_tags: List[str]
    ) -> List[str]:
        """处理所有来源标签的主函数。"""
        all_translated_tags = []

        # 1. 交互式翻译 DLsite 标签
        for tag in dlsite_tags:
            if tag in self._ignore_set:
                continue
            if tag not in self._jp_to_cn_map:
                translated = await self._handle_new_tag(
                    tag, self._jp_to_cn_map, TAG_JP_TO_CN_PATH, "DLsite"
                )
                if translated:
                    all_translated_tags.append(translated)
            else:
                all_translated_tags.append(self._jp_to_cn_map[tag])

        # 2. 交互式翻译 Fanza 标签
        for tag in fanza_tags:
            if tag in self._ignore_set:
                continue
            if tag not in self._fanza_to_cn_map:
                translated = await self._handle_new_tag(
                    tag, self._fanza_to_cn_map, TAG_FANZA_TO_CN_PATH, "Fanza"
                )
                if translated:
                    all_translated_tags.append(translated)
            else:
                all_translated_tags.append(self._fanza_to_cn_map[tag])

        # 3. 处理 GGBases 标签 (非交互)
        for tag in ggbases_tags:
            translated = self._ggbase_map.get(tag, tag) or tag
            if translated:
                all_translated_tags.append(translated)

        # 4. 统一进行归一化映射
        mapped_set: Set[str] = set()
        for tag in all_translated_tags:
            if not tag:
                continue
            tag_lower = tag.strip().lower()
            if tag_lower in self._reverse_mapping_dict:
                mapped_set.add(self._reverse_mapping_dict[tag_lower])
            else:
                mapped_set.add(tag.strip())

        return sorted(list(mapped_set))
