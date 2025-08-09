# core/game_processor.py
# 该模块用于处理游戏数据的同步和处理逻辑
import re

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
    # --- 辅助函数 split_to_list, split_work_types, choose_cover_url 不变 ---
    def split_to_list(text):
        if not text:
            return []
        if isinstance(text, list):
            return text
        return [s.strip() for s in re.split(r"[、/\n]", text) if s.strip()]

    def split_work_types(text):
        if not text:
            return []
        if isinstance(text, list):
            return text
        return [s.strip() for s in re.split(r"[、/・|｜,，\n]", text) if s.strip()]

    source = (source or game.get("source", "unknown")).lower()

    ggbases_info = ggbases_info or {}
    bangumi_info = bangumi_info or {}

    def choose_cover_url(
        source_str: str, detail_dict: dict, bangumi_dict: dict, ggbases_dict: dict
    ) -> str:
        cover_url = None
        if source_str == "dlsite":
            cover_url = detail_dict.get("封面图链接") or detail_dict.get("封面图")
            if not cover_url:
                cover_url = ggbases_dict.get("封面图链接")
            if not cover_url:
                cover_url = bangumi_dict.get("封面图链接") or bangumi_dict.get("image")
        elif source_str == "getchu":
            cover_url = bangumi_dict.get("封面图链接") or bangumi_dict.get("image")
            if not cover_url:
                cover_url = ggbases_dict.get("封面图链接")
            if not cover_url:
                cover_url = detail_dict.get("封面图链接") or detail_dict.get("封面图")
            if cover_url and not cover_url.startswith("http"):
                cover_url = "https://www.getchu.com" + cover_url
        else:
            cover_url = bangumi_dict.get("封面图链接") or bangumi_dict.get("image")
            if not cover_url:
                cover_url = ggbases_dict.get("封面图链接")
            if not cover_url:
                cover_url = detail_dict.get("封面图链接") or detail_dict.get("封面图")
        return cover_url

    # --- 标签和数据合并逻辑不变 ---
    dlsite_tags_raw = detail.get("标签", [])
    if not isinstance(dlsite_tags_raw, list):
        dlsite_tags_raw = [dlsite_tags_raw]

    ggbases_tags_raw = ggbases_info.get("标签", [])
    if not isinstance(ggbases_tags_raw, list):
        ggbases_tags_raw = [ggbases_tags_raw]

    mapped_dlsite_tags = map_and_translate_tags(dlsite_tags_raw, source="dlsite")
    mapped_ggbases_tags = map_and_translate_tags(ggbases_tags_raw, source="ggbase")
    mapped_tags = sorted(set(mapped_dlsite_tags + mapped_ggbases_tags))
    cover_url = choose_cover_url(source, detail, bangumi_info, ggbases_info)

    merged = {
        "title": (
            bangumi_info.get("title")
            or bangumi_info.get("title_cn")
            or game.get("notion_title")
            or game.get("title")
        ),
        "游戏别名": bangumi_info.get("title_cn") or "",
        "url": game.get("url"),
        "价格": game.get("价格") or game.get("price"),
        "品牌": detail.get("品牌"),
        "链接": game.get("url"),
        "封面图链接": cover_url,
        "发售日": detail.get("发售日") or detail.get("発売日"),
        "剧本": split_to_list(detail.get("剧本") or detail.get("シナリオ")),
        "原画": split_to_list(detail.get("原画") or detail.get("原画家")),
        "声优": split_to_list(detail.get("声优") or detail.get("CV")),
        "音乐": split_to_list(detail.get("音乐") or detail.get("音楽")),
        "作品形式": split_work_types(detail.get("作品形式") or detail.get("ジャンル")),
        "大小": size,
        "资源链接": ggbases_detail_url,
        "标签": mapped_tags,
        "游戏简介": bangumi_info.get("summary") or "",
    }

    page_id = await notion_client.create_or_update_game(
        merged, brand_relation_id=brand_id, page_id=selected_similar_page_id
    )
    return page_id
