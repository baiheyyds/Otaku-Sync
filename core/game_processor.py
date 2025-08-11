# core/game_processor.py
import re  # 确保文件顶部导入 re

from utils import logger
from utils.tag_mapping import map_and_translate_tags


async def process_and_sync_game(
    game,
    detail,
    size,
    notion_client,
    brand_id,
    ggbases_client,
    user_keyword,
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

    list_fields_to_merge = ["剧本", "原画", "声优", "音乐"]
    fields_to_overwrite = ["发售日", "作品形式"]

    for field in list_fields_to_merge:
        bangumi_values_raw = merged.get(field, [])
        bangumi_values = []
        if isinstance(bangumi_values_raw, str):
            # --- 核心修复：使用正则表达式处理多种分隔符 ---
            bangumi_values = [
                v.strip() for v in re.split(r"[,、/]", bangumi_values_raw) if v.strip()
            ]
        elif isinstance(bangumi_values_raw, list):
            bangumi_values = bangumi_values_raw

        detail_values = detail.get(field, [])

        combined_set = set(bangumi_values) | set(detail_values)
        # 过滤掉空的字符串
        merged[field] = sorted([item for item in list(combined_set) if item])

    for field in fields_to_overwrite:
        if detail.get(field):
            merged[field] = detail[field]

    if ggbases_info.get("容量"):
        merged["大小"] = ggbases_info.get("容量")

    dlsite_tags = map_and_translate_tags(detail.get("标签", []), source="dlsite")
    ggbases_tags = map_and_translate_tags(ggbases_info.get("标签", []), source="ggbase")
    bangumi_tags_raw = merged.get("标签", [])
    bangumi_tags = []
    if isinstance(bangumi_tags_raw, str):
        bangumi_tags = [t.strip() for t in bangumi_tags_raw.split(",")]
    elif isinstance(bangumi_tags_raw, list):
        bangumi_tags = bangumi_tags_raw

    merged["标签"] = sorted(list(set(dlsite_tags + ggbases_tags + bangumi_tags)))

    merged["title"] = bangumi_info.get("title") or detail.get("标题") or game.get("title")
    merged["title_cn"] = bangumi_info.get("name_cn") or ""

    merged["封面图链接"] = (
        bangumi_info.get("封面图链接") or ggbases_info.get("封面图链接") or detail.get("封面图链接")
    )

    merged["dlsite_link"] = game.get("url") if source == "dlsite" else None
    merged["getchu_link"] = game.get("url") if source == "getchu" else None
    merged["资源链接"] = ggbases_detail_url
    merged["价格"] = game.get("价格") or game.get("price")
    merged["brand_relation_id"] = brand_id

    # 简介的key在bangumi_info中是summary, Notion中是"游戏简介"
    if not merged.get("summary") and bangumi_info.get("summary"):
        merged["summary"] = bangumi_info.get("summary")

    page_id = await notion_client.create_or_update_game(page_id=selected_similar_page_id, **merged)
    return page_id
