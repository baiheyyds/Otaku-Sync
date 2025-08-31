# core/game_processor.py
import re

from core.name_splitter import name_splitter
from utils import logger
from utils.tag_manager import TagManager  # 导入 TagManager 以便类型提示


async def process_and_sync_game(
    game,
    detail,
    notion_client,
    brand_id,
    ggbases_client,
    user_keyword,
    notion_game_schema,
    tag_manager: TagManager,  # <--- 1. 添加到函数签名中
    interactive=False,
    ggbases_detail_url=None,
    ggbases_info=None,
    bangumi_info=None,
    source=None,
    selected_similar_page_id=None,
):
    source = (source or game.get("source", "unknown")).lower()
    ggbases_info = ggbases_info or {}
    bangumi_info = bangumi_info or {}

    merged = bangumi_info.copy()

    # --- 合并字段逻辑 (无变化) ---
    list_fields_to_merge = [
        "剧本",
        "原画",
        "声优",
        "音乐",
        "作品形式",
    ]  # <-- 将"作品形式"加入合并列表
    fields_to_overwrite = ["发售日"]

    for field in list_fields_to_merge:
        # ... (此循环内部无变化) ...
        bangumi_values_raw = merged.get(field, [])
        bangumi_values = []
        if isinstance(bangumi_values_raw, str):
            bangumi_values = await name_splitter.smart_split(bangumi_values_raw)
        elif isinstance(bangumi_values_raw, list):
            bangumi_values = bangumi_values_raw
        detail_values = detail.get(field, [])
        combined_set = set(bangumi_values) | set(detail_values)
        merged[field] = sorted([item for item in list(combined_set) if item])

    for field in fields_to_overwrite:
        if detail.get(field):
            merged[field] = detail[field]

    # --- 文件大小优先级 (无变化) ---
    game_size = detail.get("容量") or ggbases_info.get("容量")
    if game_size:
        merged["大小"] = game_size

    # --- 【功能 3】调用新的 TagManager 处理所有标签 ---
    logger.system("正在处理和映射所有标签...")
    final_tags = await tag_manager.process_tags(
        dlsite_tags=detail.get("标签", []) if source == "dlsite" else [],
        fanza_tags=detail.get("标签", []) if source == "fanza" else [],
        ggbases_tags=ggbases_info.get("标签", []),
    )
    merged["标签"] = final_tags
    logger.success("标签处理完成！")

    # --- 后续数据组装 (无变化) ---
    merged["title"] = bangumi_info.get("title") or detail.get("标题") or game.get("title")
    merged["title_cn"] = bangumi_info.get("name_cn") or ""
    merged["封面图链接"] = (
        bangumi_info.get("封面图链接") or ggbases_info.get("封面图链接") or detail.get("封面图链接")
    )
    merged["dlsite_link"] = game.get("url") if source == "dlsite" else None
    merged["fanza_link"] = game.get("url") if source == "fanza" else None
    merged["资源链接"] = ggbases_detail_url
    merged["价格"] = game.get("价格") or game.get("price")
    merged["brand_relation_id"] = brand_id
    if not merged.get("summary") and bangumi_info.get("summary"):
        merged["summary"] = bangumi_info.get("summary")

    page_id = await notion_client.create_or_update_game(
        properties_schema=notion_game_schema, page_id=selected_similar_page_id, **merged
    )
    return page_id
