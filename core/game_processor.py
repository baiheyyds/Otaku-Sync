# core/game_processor.py
import re

from core.name_splitter import name_splitter  # <--- 导入新工具
from utils import logger

# 核心修复：直接从这里导入需要的函数
from utils.tag_mapping import map_tags, load_json, TAG_JP_PATH, TAG_GGBASE_PATH


async def process_and_sync_game(
    game,
    detail,
    # size, # <--- 核心修复 1: 移除这个多余且导致错误的参数
    notion_client,
    brand_id,
    ggbases_client,
    user_keyword,
    notion_game_schema,
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

    # ... (list_fields_to_merge 和 fields_to_overwrite 的逻辑不变) ...
    list_fields_to_merge = ["剧本", "原画", "声优", "音乐"]
    fields_to_overwrite = ["发售日", "作品形式"]

    for field in list_fields_to_merge:
        bangumi_values_raw = merged.get(field, [])
        bangumi_values = []
        if isinstance(bangumi_values_raw, str):
            bangumi_values = await name_splitter.smart_split(bangumi_values_raw)
        elif isinstance(bangumi_values_raw, list):
            bangumi_values = bangumi_values_raw
        detail_values = detail.get(field, [])
        combined_set = set(bangumi_values) | set(detail_values)
        merged[field] = sorted([item for item in list(combined_set) if item])

    # 注意：确保这里的字段名与你的 Notion 和其他客户端的返回一致
    # 假设 dlsite_client 和 fanza_client 都返回 "发售时间"
    for field in fields_to_overwrite:
        if detail.get(field):
            merged[field] = detail[field]

    # --- 核心修复 2: 建立正确的文件大小优先级 ---
    # 优先级: 主要来源 (DLsite/Fanza) > GGBases
    game_size = detail.get("容量") or ggbases_info.get("容量")
    if game_size:
        merged["大小"] = game_size
    # --- 修复结束 ---

    # --- [最终修复] 修正标签处理逻辑：先翻译，再合并，最后统一映射 ---

    # 1. 单独翻译来自不同来源的标签

    # 翻译 DLsite 的日文标签
    tag_jp_to_cn_map = load_json(TAG_JP_PATH)
    dlsite_raw_tags = detail.get("标签", [])
    dlsite_translated_tags = [tag_jp_to_cn_map.get(tag, tag) for tag in dlsite_raw_tags]

    # "翻译" GGBases 的标签（这里主要是为了统一格式或修正）
    tag_ggbase_map = load_json(TAG_GGBASE_PATH)
    ggbases_raw_tags = ggbases_info.get("标签", [])
    ggbases_translated_tags = [tag_ggbase_map.get(tag, tag) or tag for tag in ggbases_raw_tags]

    # 2. 将所有翻译后的标签合并到一个列表中
    all_translated_tags = dlsite_translated_tags + ggbases_translated_tags

    # 3. 对合并后的完整列表进行统一的归一化映射
    #    map_tags 函数会根据 tag_mapping_dict.json 的规则进行合并和去重
    final_mapped_tags = map_tags(all_translated_tags)

    merged["标签"] = final_mapped_tags
    # --- 修复结束 ---

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
