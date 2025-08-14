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

    # 以 Bangumi 数据为基础，它包含了所有动态映射的字段
    combined_info = bangumi_brand_info.copy() if bangumi_brand_info else {}

    # --- 使用统一的内部键名进行整合 ---

    # 整合官网: Bangumi的'homepage'字段和Getchu的URL
    # 注意：在BangumiClient中我们已经把 "官网" 映射为了 'homepage'
    combined_info["official_url"] = first_nonempty(
        combined_info.get("homepage"),
        getchu_brand_page_url,
    )

    # 整合Ci-en: Bangumi的'Ci-en'和Dlsite的'ci_en_url'
    combined_info["ci_en_url"] = first_nonempty(
        combined_info.get("Ci-en"),  # Bangumi 返回的键
        dlsite_extra_info.get("ci_en_url") if dlsite_extra_info else None,
    )

    # 整合图标: Bangumi的'icon'和Dlsite的'icon_url'
    # 注意: 在BangumiClient中我们已经把 "img" 映射为了 'icon'
    combined_info["icon_url"] = first_nonempty(
        combined_info.get("icon"),
        dlsite_extra_info.get("icon_url") if dlsite_extra_info else None,
    )

    # 整合推特
    combined_info["twitter"] = combined_info.get("twitter")

    # --- 清理掉旧的、不统一的键名，避免下游冲突 ---
    # 现在 `info` 字典中，预定义字段都使用了 'official_url' 这样的统一键名
    # 而动态字段（如 '成立时间'）则保留了其 Notion 属性名
    combined_info.pop("homepage", None)
    combined_info.pop("Ci-en", None)
    combined_info.pop("icon", None)
    combined_info.pop("Twitter", None)  # 清理掉大写的 Twitter

    return combined_info
