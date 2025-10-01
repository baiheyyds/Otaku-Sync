# core/brand_handler.py
import asyncio
from utils import logger

async def handle_brand_info(
    bangumi_brand_info: dict, dlsite_extra_info: dict, getchu_brand_page_url: str = None
) -> dict:
    """合并来自不同来源的品牌信息。"""
    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    combined_info = bangumi_brand_info.copy() if bangumi_brand_info else {}
    combined_info["official_url"] = first_nonempty(
        combined_info.get("homepage"), getchu_brand_page_url
    )
    combined_info["ci_en_url"] = first_nonempty(
        combined_info.get("Ci-en"),
        dlsite_extra_info.get("ci_en_url") if dlsite_extra_info else None,
    )
    combined_info["icon_url"] = first_nonempty(
        combined_info.get("icon"),
        dlsite_extra_info.get("icon_url") if dlsite_extra_info else None,
    )
    combined_info["twitter"] = combined_info.get("twitter")

    # 清理旧键名
    for key in ["homepage", "Ci-en", "icon", "Twitter"]:
        combined_info.pop(key, None)

    return combined_info

async def check_brand_status(context: dict, brand_name: str) -> tuple[str | None, bool]:
    """
    检查品牌的缓存和Notion状态，决定是否需要抓取新信息。
    返回 (page_id, needs_fetching)。
    """
    if not brand_name:
        return None, False

    brand_cache = context["brand_cache"]
    notion_client = context["notion"]
    page_id = None
    needs_fetching = True

    cached_details = brand_cache.get_brand_details(brand_name)
    if cached_details:
        cached_page_id = cached_details.get("page_id")
        if await notion_client.check_page_exists(cached_page_id):
            page_id = cached_page_id
            if cached_details.get("has_icon"):
                logger.cache(f"[品牌缓存] 校验通过: '{brand_name}' 信息完整，跳过抓取。")
                needs_fetching = False
        else:
            logger.warn(f"[品牌缓存] 失效: '{brand_name}' 对应的页面ID '{cached_page_id}' 在Notion中已不存在。")

    if needs_fetching and not page_id:
        notion_details = await notion_client.get_brand_details_by_name(brand_name)
        if notion_details:
            page_id = notion_details.get("page_id")
            brand_cache.add_brand(brand_name, page_id, notion_details.get("has_icon"))
            if notion_details.get("has_icon"):
                logger.cache(f"[Notion查询] 命中: '{brand_name}' 信息完整，跳过抓取。")
                needs_fetching = False
    
    return page_id, needs_fetching

async def finalize_brand_update(context: dict, brand_name: str, page_id: str | None, fetched_data: dict) -> str | None:
    """
    使用已抓取的数据，处理并更新品牌信息到Notion。
    """
    if not brand_name:
        return page_id

    final_brand_info = await handle_brand_info(
        bangumi_brand_info=fetched_data.get("bangumi_brand_info", {}),
        dlsite_extra_info=fetched_data.get("brand_extra_info", {}),
    )

    if not final_brand_info:
        logger.info(f"品牌 '{brand_name}' 没有抓取到任何新信息，跳过更新。")
        return page_id

    brand_id = await context["notion"].create_or_update_brand(
        brand_name, page_id=page_id, **final_brand_info
    )

    if brand_id:
        final_has_icon = bool(final_brand_info.get("icon_url"))
        context["brand_cache"].add_brand(brand_name, brand_id, final_has_icon)
        logger.cache(f"[品牌缓存] 已更新: '{brand_name}' (信息完整: {final_has_icon})")
    
    return brand_id