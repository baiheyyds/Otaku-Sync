import difflib
import hashlib
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


def save_cache(titles):
    valid_titles = [t for t in titles if t.get("title") and t.get("id")]
    with open(get_cache_path(), "w", encoding="utf-8") as f:
        json.dump(valid_titles, f, ensure_ascii=False, indent=2)


def hash_titles(data):
    items = sorted(f"{item.get('id')}:{item.get('title')}" for item in data if item.get("id") and item.get("title"))
    return hashlib.md5("".join(items).encode("utf-8")).hexdigest()


def load_or_update_titles(notion_client):
    """
    加载本地缓存，如与 Notion 数据不一致则更新。
    """
    path = get_cache_path()

    try:
        local_data = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                local_data = json.load(f)

        remote_data = notion_client.get_all_game_titles()
        if hash_titles(local_data) != hash_titles(remote_data):
            print("♻️ Notion 游戏标题有更新，重新缓存...")
            save_cache(remote_data)
            return remote_data

        return local_data

    except Exception as e:
        print(f"⚠️ 校验缓存失败，尝试从 Notion 拉取: {e}")
        try:
            remote_data = notion_client.get_all_game_titles()
            save_cache(remote_data)
            return remote_data
        except Exception as e2:
            print(f"❌ 无法连接 Notion，仅使用旧缓存: {e2}")
            return local_data if path.exists() else []


def filter_similar_titles(new_title, cached_titles, threshold):
    """
    返回所有可能相似的旧游戏标题
    """
    new_norm = normalize(new_title)
    candidates = []

    for item in cached_titles:
        title = item.get("title")
        norm_title = normalize(title)
        ratio = difflib.SequenceMatcher(None, norm_title, new_norm).ratio()

        if ratio >= threshold or new_norm in norm_title or norm_title in new_norm:
            # 强制给模糊包含一个较高分
            candidates.append((item, max(ratio, 0.95)))
    return candidates


def remove_invalid_pages(candidates, cached_titles, notion_client):
    """
    检查页面是否仍存在；如不存在则从缓存中删除
    """
    updated_cache = cached_titles
    valid_candidates = []
    changed = False

    for item, score in candidates:
        page_id = item.get("id")
        if page_id and notion_client.check_page_exists(page_id):
            valid_candidates.append((item, score))
        else:
            print(f"🗑️ 已失效页面：{item.get('title')}，从缓存移除")
            updated_cache = [x for x in updated_cache if x.get("id") != page_id]
            changed = True

    return valid_candidates, updated_cache, changed


def check_existing_similar_games(notion_client, new_title, cached_titles=None, threshold=0.78):
    print("🔍 正在检查是否有可能重复的游戏...")

    # 加载缓存（如未传入）
    if not cached_titles or not isinstance(cached_titles[0], dict):
        cached_titles = load_or_update_titles(notion_client)

    candidates = filter_similar_titles(new_title, cached_titles, threshold)
    valid_candidates, updated_cache, changed = remove_invalid_pages(candidates, cached_titles, notion_client)

    if changed:
        save_cache(updated_cache)
        cached_titles = updated_cache

    # 实时 Notion 搜索作为最终保障
    notion_results = notion_client.search_game(new_title)
    if notion_results:
        print("⚠️ Notion 实时搜索发现已有同名游戏：", notion_client.get_page_title(notion_results[0]) or "[未知标题]")
        valid_candidates = [(notion_results[0], 1.0)]

    if valid_candidates:
        print("⚠️ 检测到可能重复的游戏：")
        for item, score in sorted(valid_candidates, key=lambda x: x[1], reverse=True):
            title_str = (
                item.get("title") if isinstance(item, dict) and "title" in item else notion_client.get_page_title(item)
            )
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
            confirm_check = notion_client.search_game(new_title)
            if confirm_check:
                print("⚠️ 注意：你选择了新建，但 Notion 中仍存在相同标题，自动转为更新")
                return True, cached_titles, "update", confirm_check[0].get("id")
            else:
                return True, cached_titles, "create", None
    else:
        print("✅ 没有发现重复游戏")
        return True, cached_titles, "create", None
