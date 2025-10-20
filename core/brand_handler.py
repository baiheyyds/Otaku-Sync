# core/brand_handler.py
import asyncio
import logging
from rapidfuzz import fuzz, process

from utils.utils import normalize_brand_name as normalize


async def handle_brand_info(
    bangumi_brand_info: dict, dlsite_extra_info: dict
) -> dict:
    """合并来自不同来源的品牌信息。"""

    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    combined_info = bangumi_brand_info.copy() if bangumi_brand_info else {}
    combined_info["official_url"] = first_nonempty(
        combined_info.get("homepage")
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
    检查品牌的缓存和Notion状态，如果找不到精确匹配，则进行相似度检查并与用户交互。
    返回 (page_id, needs_fetching)。
    """
    if not brand_name:
        return None, False

    brand_cache = context["brand_cache"]
    notion_client = context["notion"]
    interaction_provider = context["interaction_provider"]
    brand_mapping_manager = context["brand_mapping_manager"]

    # 1. 精确匹配检查 (包括缓存和Notion)
    page_id, needs_fetching = await _find_exact_match(brand_cache, notion_client, brand_name)
    if page_id is not None:
        return page_id, needs_fetching

    # 2. 如果没有精确匹配，执行相似度搜索
    logging.info(f"🔍 品牌 ‘{brand_name}’ 无精确匹配，开始进行相似度搜索...")
    all_brand_names = list(brand_cache.cache.keys())
    if not all_brand_names:
        logging.info("🔍 品牌缓存为空，无法进行相似度搜索。将创建新品牌。")
        return None, True

    # 使用 rapidfuzz 进行模糊匹配
    # 我们只关心最佳匹配项
    best_match = process.extractOne(
        normalize(brand_name),
        [normalize(b) for b in all_brand_names],
        scorer=fuzz.WRatio,
        score_cutoff=85
    )

    if not best_match:
        logging.info(f"🔍 未找到与 ‘{brand_name}’ 相似的品牌，将创建新品牌。")
        return None, True

    # best_match 是 (normalized_name, score, index)
    # 我们需要通过 index 找回原始的、大小写正确的品牌名
    original_suggested_brand = all_brand_names[best_match[2]]

    # 3. 与用户交互确认合并
    decision = await interaction_provider.confirm_brand_merge(
        new_brand_name=brand_name,
        suggested_brand=original_suggested_brand
    )

    if decision == "merge":
        logging.info(f"🔧 用户选择合并: ‘{brand_name}’ -> ‘{original_suggested_brand}’")
        # 更新映射文件
        brand_mapping_manager.add_alias(original_suggested_brand, brand_name)
        # 从缓存获取已存在品牌的 page_id
        existing_brand_details = brand_cache.get_brand_details(original_suggested_brand)
        if existing_brand_details and existing_brand_details.get("page_id"):
            # 因为是合并到现有品牌，所以不需要重新抓取信息
            return existing_brand_details["page_id"], False
        else:
            # 这种情况很少见，但以防万一缓存出错了
            logging.warning(f"⚠️ 在缓存中找不到 ‘{original_suggested_brand}’ 的页面ID，将继续创建流程。")
            return None, True

    elif decision == "create":
        logging.info(f"🔧 用户选择为 ‘{brand_name}’ 创建新品牌。")
        return None, True
    else:  # decision == "cancel" or None
        logging.warning(f"⚠️ 用户取消了品牌 ‘{brand_name}’ 的处理。")
        return None, False # 中止此品牌的处理


async def _find_exact_match(brand_cache, notion_client, brand_name):
    """Helper function to check for an exact brand match in cache and Notion."""
    cached_details = brand_cache.get_brand_details(brand_name)
    if cached_details:
        cached_page_id = cached_details.get("page_id")
        if await notion_client.check_page_exists(cached_page_id):
            page_id = cached_page_id
            needs_fetching = not cached_details.get("has_icon", False)
            if not needs_fetching:
                logging.info(f"🗂️ [品牌缓存] 命中且信息完整: ‘{brand_name}’，跳过抓取。")
            else:
                logging.info(f"🗂️ [品牌缓存] 命中但信息不完整: ‘{brand_name}’，需要抓取。")
            return page_id, needs_fetching
        else:
            logging.warning(f"⚠️ [品牌缓存] 失效: ‘{brand_name}’ 对应的页面ID ‘{cached_page_id}’ 在Notion中已不存在。")

    notion_details = await notion_client.get_brand_details_by_name(brand_name)
    if notion_details:
        page_id = notion_details.get("page_id")
        has_icon = notion_details.get("has_icon", False)
        brand_cache.add_brand(brand_name, page_id, has_icon)
        needs_fetching = not has_icon
        if not needs_fetching:
            logging.info(f"🗂️ [Notion查询] 命中且信息完整: ‘{brand_name}’，跳过抓取。")
        else:
            logging.info(f"🗂️ [Notion查询] 命中但信息不完整: ‘{brand_name}’，需要抓取。")
        return page_id, needs_fetching

    return None, True

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
        logging.info(f"🔍 品牌 '{brand_name}' 没有抓取到任何新信息，跳过更新。")
        return page_id

    brand_id = await context["notion"].create_or_update_brand(
        brand_name, page_id=page_id, **final_brand_info
    )

    if brand_id:
        final_has_icon = bool(final_brand_info.get("icon_url"))
        context["brand_cache"].add_brand(brand_name, brand_id, final_has_icon)
        logging.info(f"🗂️ [品牌缓存] 已更新: '{brand_name}' (信息完整: {final_has_icon})")
    
    return brand_id
