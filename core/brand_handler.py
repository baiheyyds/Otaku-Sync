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

    bangumi_info_task = (
        asyncio.create_task(bangumi_client.fetch_brand_info_from_bangumi(brand_name))
        if bangumi_client
        else None
    )

    bangumi_info = {}
    if bangumi_info_task:
        try:
            bangumi_info = (await bangumi_info_task) or {}
            if bangumi_info:
                logger.success(f"[{brand_name}] 从 Bangumi 获取品牌信息成功")
        except Exception as e:
            logger.warn(f"[{brand_name}] Bangumi品牌信息抓取异常: {e}")

    extra = {}
    if brand_page_url and brand_page_url in cache:
        extra = cache[brand_page_url]
        logger.cache(f"[{brand_name}] 使用品牌缓存")

    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    # --- 核心改动：分离官网和 Ci-en 的数据源 ---
    combined_info = {
        "official_url": first_nonempty(
            bangumi_info.get("homepage"),
            getchu_brand_page_url,  # Getchu 的品牌链接是真正的官网
            brand_homepage,
        ),
        "ci_en_url": first_nonempty(
            extra.get("ci_en_url"),  # Dlsite 的链接现在只提供给 Ci-en
        ),
        "icon_url": first_nonempty(
            bangumi_info.get("icon"),
            extra.get("icon_url"),  # Dlsite 的图标可以继续使用
            brand_icon,
        ),
        "summary": first_nonempty(bangumi_info.get("summary"), extra.get("简介")),
        "bangumi_url": bangumi_info.get("bangumi_url"),
        "company_address": first_nonempty(
            bangumi_info.get("company_address"), extra.get("公司地址")
        ),
        "birthday": first_nonempty(bangumi_info.get("birthday"), extra.get("生日")),
        "alias": first_nonempty(bangumi_info.get("alias"), extra.get("别名")),
        "twitter": first_nonempty(bangumi_info.get("twitter"), extra.get("推特")),
    }
    # --- 核心改动结束 ---

    return await notion_client.create_or_update_brand(brand_name, **combined_info)
