# utils/tag_mapping.py
# 该模块用于处理标签映射和翻译
import json
import os

# 🔧 JSON 文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG_JP_PATH = os.path.join(BASE_DIR, "mapping", "tag_jp_to_cn.json")
TAG_GGBASE_PATH = os.path.join(BASE_DIR, "mapping", "tag_ggbase.json")
TAG_MAPPING_PATH = os.path.join(BASE_DIR, "mapping", "tag_mapping_dict.json")


def load_json(path):
    """安全地加载JSON文件，如果文件不存在或为空则返回空字典。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def process_all_tags(dlsite_tags: list = None, ggbases_tags: list = None) -> list:
    """
    【核心修复函数】
    统一处理所有来源的标签。
    1. 分别翻译来自 DLsite 和 GGBases 的标签。
    2. 将翻译后的标签合并。
    3. 对合并后的列表进行最终的归一化映射。
    """
    dlsite_tags = dlsite_tags or []
    ggbases_tags = ggbases_tags or []

    # --- 1. 翻译 ---
    tag_jp_to_cn_map = load_json(TAG_JP_PATH)
    translated_dlsite = [tag_jp_to_cn_map.get(tag.strip(), tag.strip()) for tag in dlsite_tags]

    tag_ggbase_map = load_json(TAG_GGBASE_PATH)
    translated_ggbases = [
        (tag_ggbase_map.get(tag.strip(), tag.strip()) or tag.strip()) for tag in ggbases_tags
    ]

    # --- 2. 合并 ---
    all_translated_tags = translated_dlsite + translated_ggbases

    # --- 3. 归一化映射 ---
    mapping_dict = load_json(TAG_MAPPING_PATH)
    if not mapping_dict:
        # 如果没有映射规则，直接返回去重并排序的翻译后标签
        return sorted(list(set(tag for tag in all_translated_tags if tag)))

    # 构建一个反向映射，将所有别名指向其主标签
    # 例如：{'母乳': '母乳/...', '喷乳': '母乳/...'}
    reverse_map = {}
    for main_tag, keywords in mapping_dict.items():
        for keyword in keywords:
            # 使用 .lower() 来进行不区分大小写的匹配
            reverse_map[keyword.strip().lower()] = main_tag

    mapped_set = set()
    for tag in all_translated_tags:
        if not tag:
            continue

        # 同样使用 .lower() 来查找
        tag_lower = tag.strip().lower()

        # 查找是否存在映射规则，如果存在，则添加主标签
        if tag_lower in reverse_map:
            mapped_set.add(reverse_map[tag_lower])
        else:
            # 如果没有映射规则，则保留原始（已翻译）的标签
            mapped_set.add(tag.strip())

    return sorted(list(mapped_set))


# --- 保留旧函数以防万一，但它们不再被核心流程使用 ---
def map_and_translate_tags(raw_tags, source="dlsite"):
    if source == "dlsite":
        return process_all_tags(dlsite_tags=raw_tags)
    elif source == "ggbase":
        return process_all_tags(ggbases_tags=raw_tags)
    return sorted(list(set(raw_tags)))


def map_tags(raw_tags):
    return process_all_tags(dlsite_tags=raw_tags)
