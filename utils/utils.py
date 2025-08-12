# utils/utils.py
# 该模块包含一些通用的工具函数
import re
from datetime import datetime


def extract_main_keyword(raw_keyword):
    pattern = re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FFA-Za-z0-9\-〜～]+")
    matches = pattern.findall(raw_keyword)
    if matches:
        return matches[0]
    return raw_keyword.strip()


def convert_date_jp_to_iso(date_str):
    if not date_str:
        return None

    # --- 核心修复：在处理前，先剔除可能存在的时间部分 ---
    # 这能让 "2021/07/30 00:00" 变为 "2021/07/30"
    date_str = date_str.strip().split(" ")[0]
    # --- 修复结束 ---

    # 先尝试匹配“YYYY年M月D日”格式
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        y, mo, d = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).date().isoformat()
        except ValueError:
            return None

    # 尝试 YYYY/MM/DD 或 YYYY-MM-DD 格式
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue

    return None
