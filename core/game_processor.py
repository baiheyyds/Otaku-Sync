# core/game_processor.py
# 该模块用于处理游戏数据的同步和处理逻辑
import re
from utils.tag_mapping import map_and_translate_tags
from config.config_fields import FIELDS

def process_and_sync_game(game, detail, size, notion_client, brand_id, ggbases_client, user_keyword,
                         interactive=False, ggbases_detail_url=None, ggbases_info=None, source=None,
                         selected_similar_page_id=None):
    def split_to_list(text):
        if not text:
            return []
        if isinstance(text, list):
            return text
        return [s.strip() for s in re.split(r'[、/\n]', text) if s.strip()]

    def split_work_types(text):
        if not text:
            return []
        if isinstance(text, list):
            return text
        return [s.strip() for s in re.split(r'[、/・|｜,，\n]', text) if s.strip()]

    # 优先用传入的 source 参数，如果没有则从 game 中取
    if source is None:
        source = game.get("source", "unknown").lower()
    else:
        source = source.lower()

    # ✅ 查重逻辑应已提前至 main.py 执行，无需在此重复判断

    # 优先使用传入的 ggbases_info 避免重复请求
    if ggbases_info is None:
        if ggbases_detail_url:
            try:
                ggbases_info = ggbases_client.get_info_by_url(ggbases_detail_url)
            except Exception as e:
                print(f"⚠️ 通过传入的详情页 URL 获取 GGBases 信息失败: {e}")
                ggbases_info = {}
        else:
            try:
                html = ggbases_client.get_search_page_html(user_keyword)
                ggbases_url = ggbases_client.choose_or_parse_popular_url(html, interactive=interactive)
                ggbases_info = ggbases_client.get_info_by_url(ggbases_url) if ggbases_url else {}
            except Exception as e:
                print(f"⚠️ 获取 GGBases 信息失败: {e}")
                ggbases_info = {}

    # 封面图选择逻辑
    if source == "dlsite":
        cover_url = detail.get("封面图链接") or detail.get("封面图")
    elif source == "getchu":
        cover_url = ggbases_info.get("封面图链接") or detail.get("封面图链接") or detail.get("封面图")
        if cover_url and not cover_url.startswith("http"):
            cover_url = "https://www.getchu.com" + cover_url
    else:
        cover_url = ggbases_info.get("封面图链接") or detail.get("封面图链接") or detail.get("封面图")

    # 标签处理
    dlsite_tags_raw = detail.get("标签", [])
    if not isinstance(dlsite_tags_raw, list):
        dlsite_tags_raw = [dlsite_tags_raw]

    ggbases_tags_raw = ggbases_info.get("标签", [])
    if not isinstance(ggbases_tags_raw, list):
        ggbases_tags_raw = [ggbases_tags_raw]

    mapped_dlsite_tags = map_and_translate_tags(dlsite_tags_raw, source="dlsite")
    mapped_ggbases_tags = map_and_translate_tags(ggbases_tags_raw, source="ggbase")
    mapped_tags = sorted(set(mapped_dlsite_tags + mapped_ggbases_tags))

    merged = {
        "title": game.get("title"),
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
    }

    notion_client.create_or_update_game(
        merged,
        brand_relation_id=brand_id,
        page_id=selected_similar_page_id
    )
