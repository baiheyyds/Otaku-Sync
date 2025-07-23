# 该模块用于检查游戏标题的相似性，避免重复创建游戏条目
# utils/similarity_check.py
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path


def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", "", text)
    return text


def get_cache_path():
    base_dir = Path(sys.argv[0]).resolve().parent
    cache_dir = base_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "game_titles_cache.json"


def load_cache(notion_client=None, force_refresh=False):
    path = get_cache_path()

    # 强制刷新或文件不存在
    if force_refresh or not path.exists():
        if notion_client:
            print("📥 [刷新缓存] 从 Notion 拉取游戏标题...")
            data = notion_client.get_all_game_titles()
            save_cache(data)
            return data
        return []

    # 正常加载缓存
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
            if not cached and notion_client:
                print("📥 缓存为空，尝试从 Notion 获取...")
                data = notion_client.get_all_game_titles()
                save_cache(data)
                return data
            return cached
    except Exception:
        return []


def save_cache(titles):
    # 缓存写入前过滤掉没有 id 的无效项
    valid_titles = [t for t in titles if t.get("title") and t.get("id")]
    path = get_cache_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(valid_titles, f, ensure_ascii=False, indent=2)


def check_existing_similar_games(notion_client, new_title, cached_titles=None, threshold=0.78):
    print("🔍 正在检查是否有可能重复的游戏...")

    # 1. 载入缓存，如果无效就从 Notion 拉一遍
    if not cached_titles or isinstance(cached_titles[0], str):
        cached_titles = load_cache(notion_client=notion_client, force_refresh=True)

    new_norm = normalize(new_title)
    candidates = []
    for item in cached_titles:
        title = item.get("title") if isinstance(item, dict) else str(item)
        norm_title = normalize(title)
        ratio = difflib.SequenceMatcher(None, norm_title, new_norm).ratio()

        if ratio >= threshold or new_norm in norm_title or norm_title in new_norm:
            candidates.append((item, ratio if ratio >= threshold else 0.95))

    # 过滤缓存中已删除页面
    valid_candidates = []
    for item, ratio in candidates:
        page_id = item.get("id")
        if page_id and notion_client.check_page_exists(page_id):
            valid_candidates.append((item, ratio))
        else:
            print(f"🗑️ 缓存中已删除页面：{item.get('title')}，移除...")
            cached_titles = [x for x in cached_titles if x.get("id") != page_id]
            save_cache(cached_titles)

    # **实时 Notion 搜索最终确认是否存在游戏**
    notion_results = notion_client.search_game(new_title)
    if notion_results:
        print("⚠️ Notion 实时查询发现已有同名游戏：", notion_client.get_page_title(notion_results[0]) or "[无法获取标题]")
        # 以 Notion 搜索结果为准覆盖缓存结果
        valid_candidates = [(notion_results[0], 1.0)]

    if valid_candidates:
        print("⚠️ 检测到可能重复的游戏：")
        for item, score in sorted(valid_candidates, key=lambda x: x[1], reverse=True):
            title_str = item.get("title") if isinstance(item, dict) and "title" in item else notion_client.get_page_title(item)
            print(f"  - {title_str}（相似度：{score:.2f}）")

        print("请选择操作：")
        print("1. ✅ 创建为新游戏")
        print("2. 🔄 更新已有游戏（覆盖）")
        print("3. ⛔ 跳过该游戏")

        while True:
            choice = input("请输入数字 1/2/3 并回车：").strip()
            if choice in {"1", "2", "3"}:
                break

        if choice == "3":
            return False, cached_titles, None, None
        elif choice == "2":
            return True, cached_titles, "update", valid_candidates[0][0].get("id")
        else:
            # 再确认一次避免误判
            confirm_check = notion_client.search_game(new_title)
            if confirm_check:
                print(f"⚠️ 注意：你选择了新建，但 Notion 中仍存在相同标题，自动转为更新")
                return True, cached_titles, "update", confirm_check[0].get("id")
            else:
                return True, cached_titles, "create", None
    else:
        print("✅ 没有发现重复游戏")
        return True, cached_titles, "create", None
