# utils/similarity_check.py
import asyncio
from rapidfuzz import fuzz
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

from utils import logger

async def find_similar_games_non_interactive(
    notion_client, new_title, cached_titles=None, threshold=0.78
):
    """Non-interactively finds similar games and returns candidates."""
    if not cached_titles or not isinstance(cached_titles[0], dict):
        cached_titles = await load_or_update_titles(notion_client)

    candidates = filter_similar_titles(new_title, cached_titles, threshold)
    valid_candidates, updated_cache, changed = await remove_invalid_pages(
        candidates, cached_titles, notion_client
    )

    if changed:
        save_cache(updated_cache)
        cached_titles = updated_cache

    notion_results = await notion_client.search_game(new_title)
    if notion_results:
        existing_page_data = {"id": notion_results[0]["id"], "title": new_title}
        valid_candidates = [
            (p, s) for p, s in valid_candidates if p["id"] != existing_page_data["id"]
        ]
        valid_candidates.insert(0, (existing_page_data, 1.0))
    
    return sorted(valid_candidates, key=lambda x: x[1], reverse=True), cached_titles

def load_cache_quick():
    path = get_cache_path()
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warn(f"本地缓存读取失败: {e}")
    return []


# --- normalize, get_cache_path, save_cache, hash_titles 函数不变 ---
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
    try:
        valid_titles = [t for t in titles if t.get("title") and t.get("id")]
        if not valid_titles:
            return
        with open(get_cache_path(), "w", encoding="utf-8") as f:
            json.dump(valid_titles, f, ensure_ascii=False, indent=2)
        logger.cache(f"游戏标题缓存成功写入，条目数: {len(valid_titles)}")
    except Exception as e:
        logger.error(f"缓存写入失败: {e}")


def hash_titles(data):
    items = sorted(
        f'{item.get("id")}:{item.get("title")}'
        for item in data
        if item.get("id") and item.get("title")
    )
    return hashlib.md5("".join(items).encode("utf-8")).hexdigest()


async def load_or_update_titles(notion_client):
    path = get_cache_path()
    try:
        local_data = load_cache_quick()
        remote_data = await notion_client.get_all_game_titles()
        if hash_titles(local_data) != hash_titles(remote_data):
            logger.system("Notion 游戏标题有更新，重新缓存...")
            save_cache(remote_data)
            return remote_data
        return local_data
    except Exception as e:
        logger.warn(f"校验缓存失败，尝试从 Notion 拉取: {e}")
        try:
            remote_data = await notion_client.get_all_game_titles()
            save_cache(remote_data)
            return remote_data
        except Exception as e2:
            logger.error(f"无法连接 Notion，仅使用旧缓存: {e2}")
            return load_cache_quick()

def filter_similar_titles(new_title, cached_titles, threshold):
    new_norm = normalize(new_title)
    candidates = []
    for item in cached_titles:
        title = item.get("title")
        norm_title = normalize(title)
        ratio = fuzz.ratio(norm_title, new_norm) / 100.0
        if ratio >= threshold or new_norm in norm_title or norm_title in new_norm:
            candidates.append((item, max(ratio, 0.95)))
    return candidates


async def remove_invalid_pages(candidates, cached_titles, notion_client):
    updated_cache = list(cached_titles)
    valid_candidates = []
    changed = False

    # 并发检查页面是否存在
    tasks = [notion_client.check_page_exists(item.get("id")) for item, score in candidates]
    results = await asyncio.gather(*tasks)

    for (item, score), exists in zip(candidates, results):
        page_id = item.get("id")
        if page_id and exists:
            valid_candidates.append((item, score))
        else:
            logger.warn(f"已失效页面：{item.get('title')}，从缓存移除")
            updated_cache = [x for x in updated_cache if x.get("id") != page_id]
            changed = True
    return valid_candidates, updated_cache, changed


async def check_existing_similar_games(
    notion_client, new_title, cached_titles=None, threshold=0.78
):
    logger.info("正在检查是否有可能重复的游戏...")

    if not cached_titles or not isinstance(cached_titles[0], dict):
        cached_titles = await load_or_update_titles(notion_client)

    candidates = filter_similar_titles(new_title, cached_titles, threshold)
    valid_candidates, updated_cache, changed = await remove_invalid_pages(
        candidates, cached_titles, notion_client
    )

    if changed:
        save_cache(updated_cache)
        cached_titles = updated_cache

    notion_results = await notion_client.search_game(new_title)
    if notion_results:
        logger.warn(
            f"Notion 实时搜索发现已有同名游戏：{notion_client.get_page_title(notion_results[0]) or '[未知标题]'}"
        )
        existing_page_data = {"id": notion_results[0]["id"], "title": new_title}
        valid_candidates = [
            (p, s) for p, s in valid_candidates if p["id"] != existing_page_data["id"]
        ]
        valid_candidates.insert(0, (existing_page_data, 1.0))

    if not valid_candidates:
        logger.success("没有发现重复游戏，将创建新条目。")
        return True, cached_titles, "create", None

    # 将阻塞的 input 调用放到线程中执行
    def _interactive_selection():
        logger.warn("检测到可能重复的游戏：")
        sorted_candidates = sorted(valid_candidates, key=lambda x: x[1], reverse=True)
        for i, (item, score) in enumerate(sorted_candidates):
            title_str = item.get("title") or notion_client.get_page_title(item)
            print(f"  [{i+1}] {title_str}（相似度：{score:.2f}）")

        print("\n请选择操作：")
        print("  [u] 更新最相似的游戏（默认）")
        print("  [c] 强制创建为新游戏")
        print("  [s] 跳过该游戏")

        while True:
            choice = input("请输入字母 u/c/s 并回车：").strip().lower()
            if choice in {"u", "c", "s", ""}:
                break

        return choice, sorted_candidates

    choice, sorted_candidates = await asyncio.to_thread(_interactive_selection)

    if choice == "s":
        logger.info("已选择跳过。 ולאחר מכן")
        return False, cached_titles, "skip", None
    elif choice == "c":
        # 强制创建前再次检查，因为用户输入时可能有其他进程写入了
        confirm_check = await notion_client.search_game(new_title)
        if confirm_check:
            logger.warn("注意：你选择了强制新建，但Notion中已存在完全同名的游戏，自动转为更新。")
            return True, cached_titles, "update", confirm_check[0].get("id")
        else:
            logger.success("确认创建为新游戏。 ולאחר מכן")
            return True, cached_titles, "create", None
    else:  # 默认为 u
        selected_id = sorted_candidates[0][0].get("id")
        logger.info(f"已选择更新游戏：{sorted_candidates[0][0].get('title')}")
        return True, cached_titles, "update", selected_id

def get_close_matches_with_ratio(query, candidates, limit=3, threshold=0.6):
    """Finds close matches, giving a strong boost to substring matches."""
    if not query or not candidates:
        return []

    scored_candidates = []
    for cand in candidates:
        # Start with the rapidfuzz ratio
        ratio = fuzz.ratio(query, cand) / 100.0

        # Boost score significantly if one is a substring of the other
        if query.startswith(cand) or cand.startswith(query):
            # This is a very strong indicator, especially for cases like '售价' vs '售价-初回限定版'
            ratio = max(ratio, 0.9) 
        elif cand in query:
            ratio = max(ratio, 0.8) # A slightly lower boost for contains

        if ratio >= threshold:
            scored_candidates.append((cand, ratio))

    # Sort by score (descending) and then alphabetically (ascending)
    scored_candidates.sort(key=lambda x: (-x[1], x[0]))

    # Return only the names of the top candidates
    return [cand for cand, score in scored_candidates[:limit]]