# utils/tag_logger.py
# 该模块用于记录和管理标签映射
import json
import os

from utils import logger


def load_tag_dict(file_path):
    """读取 JSON 格式的标签映射"""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tag_dict(file_path, tag_dict):
    """将标签映射 dict 写入 JSON 文件"""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(tag_dict, f, ensure_ascii=False, indent=2)


def append_new_tags(file_path, new_tags):
    """将新标签追加到 JSON 文件中，未映射内容设为空字符串"""
    tag_dict = load_tag_dict(file_path)
    added = []
    for tag in new_tags:
        tag = tag.strip()
        if tag and tag not in tag_dict:
            tag_dict[tag] = ""
            added.append(tag)

    if added:
        logger.info(f"新增标签 {len(added)} 条，已记录到 {os.path.basename(file_path)}")

    save_tag_dict(file_path, tag_dict)
    return added
