# core/brand_handler.py
import json
import os

from utils import logger

mapping_path = os.path.join(os.path.dirname(__file__), "../mapping/brand_mapping.json")
try:
    with open(mapping_path, "r", encoding="utf-8") as f:
        brand_mapping = json.load(f)
except FileNotFoundError:
    brand_mapping = {}


# --- 请用下面的代码替换整个 handle_brand_info 函数 ---


async def handle_brand_info(
    bangumi_brand_info: dict, dlsite_extra_info: dict, getchu_brand_page_url: str = None
) -> dict:

    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    # 以 Bangumi 数据为基础
    combined_info = bangumi_brand_info.copy() if bangumi_brand_info else {}

    # 整合官网
    combined_info["official_url"] = first_nonempty(
        combined_info.get("homepage"),  # Bangumi 返回的官网键可能是 homepage
        getchu_brand_page_url,
    )

    # 整合 Ci-en
    combined_info["ci_en_url"] = first_nonempty(
        combined_info.get("Ci-en"),  # 尝试从 Bangumi 获取
        dlsite_extra_info.get("ci_en_url") if dlsite_extra_info else None,  # 其次从 Dlsite 获取
    )

    # 整合图标
    combined_info["icon_url"] = first_nonempty(
        combined_info.get("icon"),  # 尝试从 Bangumi 获取
        dlsite_extra_info.get("icon_url") if dlsite_extra_info else None,  # 其次从 Dlsite 获取
    )

    # 【核心修复】清理掉旧的、不统一的键名，避免下游冲突
    combined_info.pop("homepage", None)
    combined_info.pop("Ci-en", None)
    combined_info.pop("icon", None)

    return combined_info
