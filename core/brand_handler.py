# core/brand_handler.py
# 该模块用于处理品牌信息的获取和存储
import asyncio
import json
import os

from utils import logger

mapping_path = os.path.join(os.path.dirname(__file__), "../mapping/brand_mapping.json")
with open(mapping_path, "r", encoding="utf-8") as f:
    brand_mapping = json.load(f)


async def handle_brand_info(
    source,
    dlsite_client,
    notion_client,
    brand_name,
    brand_page_url,
    cache,
    brand_homepage=None,
    brand_icon=None,
    bangumi_client=None,
    getchu_client=None,
    getchu_brand_page_url=None,
):
    if not brand_name:
        logger.warn("品牌名为空，跳过品牌处理")
        return None

    for canonical, aliases in brand_mapping.items():
        if brand_name == canonical or brand_name in aliases:
            brand_name = canonical
            break

    # 1. 从 Bangumi 获取信息作为基础数据
    bangumi_info = {}
    if bangumi_client:
        try:
            bangumi_info = await bangumi_client.fetch_brand_info_from_bangumi(brand_name) or {}
            if bangumi_info:
                logger.success(f"[{brand_name}] 从 Bangumi 获取品牌信息成功")
        except Exception as e:
            logger.warn(f"[{brand_name}] Bangumi品牌信息抓取异常: {e}")

    # 2. 从缓存（Dlsite Selenium 结果）获取补充信息
    extra = {}
    if brand_page_url and brand_page_url in cache:
        extra = cache[brand_page_url]
        logger.cache(f"[{brand_name}] 使用品牌缓存")

    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    # 3. 整合所有来源的数据，并将键名统一为 notion_client 期望的格式
    combined_info = bangumi_info.copy()

    # 整合官网
    combined_info["official_url"] = first_nonempty(
        bangumi_info.get("homepage"),
        getchu_brand_page_url,
        brand_homepage,
    )

    # 整合 Ci-en 链接
    combined_info["ci_en_url"] = first_nonempty(
        bangumi_info.get("Ci-en"),  # Bangumi 的 infobox 可能有 Ci-en
        extra.get("ci_en_url"),
    )

    # 【关键修复】整合图标链接，将 bangumi 的 'icon' 键映射到 'icon_url'
    combined_info["icon_url"] = first_nonempty(
        bangumi_info.get("icon"),  # Bangumi 来源
        extra.get("icon_url"),  # Dlsite 来源
        brand_icon,  # Getchu 来源 (如果未来有)
    )

    # 4. 清理掉临时的或已转换的旧键名，避免混淆
    combined_info.pop("homepage", None)
    combined_info.pop("icon", None)

    # 5. 将整理好的数据包传递给 notion_client
    return await notion_client.create_or_update_brand(brand_name, **combined_info)
