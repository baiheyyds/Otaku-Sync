# utils/utils.py
# 该模块包含一些通用的工具函数
import re
from datetime import datetime

def extract_main_keyword(raw_keyword):
    pattern = re.compile(r'[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FFA-Za-z0-9\-〜～]+')
    matches = pattern.findall(raw_keyword)
    if matches:
        return matches[0]
    return raw_keyword.strip()

def convert_date_jp_to_iso(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()

    # 先尝试匹配“YYYY年M月D日”格式
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
    if m:
        y, mo, d = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d))
            return dt.date().isoformat()
        except:
            return None
    
    # 尝试 YYYY/MM/DD 或 YYYY-MM-DD 格式
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.date().isoformat()
        except:
            continue

    return None
