# utils/tag_mapping.py
import os
import json

# 🔧 JSON 文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG_JP_PATH = os.path.join(BASE_DIR, "mapping", "tag_jp_to_cn.json")
TAG_GGBASE_PATH = os.path.join(BASE_DIR, "mapping", "tag_ggbase.json")
TAG_MAPPING_PATH = os.path.join(BASE_DIR, "mapping", "tag_mapping_dict.json")


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def map_and_translate_tags(raw_tags, source="dlsite"):
    """翻译标签并统一映射"""
    raw_tags = [tag.strip() for tag in raw_tags if tag.strip()]

    if source == "dlsite":
        tag_jp_to_cn = load_json(TAG_JP_PATH)
        translated = [tag_jp_to_cn.get(tag, tag) for tag in raw_tags]

    elif source == "ggbase":
        tag_ggbase = load_json(TAG_GGBASE_PATH)
        translated = [tag_ggbase.get(tag, tag) or tag for tag in raw_tags]

    else:
        translated = raw_tags

    return sorted(set(map_tags(translated)))

def map_tags(raw_tags):
    """标签归一化映射"""
    mapping = load_json(TAG_MAPPING_PATH)

    reverse_map = {}
    for main_tag, keywords in mapping.items():
        for keyword in keywords:
            reverse_map[keyword.lower()] = main_tag

    mapped_set = set()
    for tag in raw_tags:
        tag_key = tag.strip()
        tag_key_lower = tag_key.lower()
        if tag_key_lower in reverse_map:
            mapped_set.add(reverse_map[tag_key_lower])
        else:
            mapped_set.add(tag_key)  # 保留原标签

    return sorted(mapped_set)
