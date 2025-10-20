# utils/similarity_check.py
import asyncio
import hashlib
import json
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

# --- Constants ---
N_GRAM_SIZE = 2

# --- Helper Functions ---
def normalize(text):
    """
    Aggressively normalize text for similarity comparison.
    - Converts to NFKC for character consistency.
    - Converts to lowercase.
    - Removes all whitespace and a wide range of symbols/punctuations.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    # Expanded regex to remove spaces, hyphens, colons, brackets, tildes, etc.
    text = re.sub(r"[\s\-_:()[\].【】~～「」『』]+", "", text)
    return text

def get_ngrams(text, n):
    """Generates n-grams for a given text."""
    return {text[i:i+n] for i in range(len(text) - n + 1)}

class SimilarityChecker:
    def __init__(self, cached_titles):
        self.cached_titles = cached_titles
        self.norm_titles = [normalize(item.get("title", "")) for item in self.cached_titles]
        self.index = self._build_index()

    def _build_index(self):
        index = defaultdict(set)
        for i, norm_title in enumerate(self.norm_titles):
            if not norm_title:
                continue
            for ngram in get_ngrams(norm_title, N_GRAM_SIZE):
                index[ngram].add(i)
        return index

    def filter_similar_titles(self, new_title, threshold):
        new_norm = normalize(new_title)
        if not new_norm:
            return []

        candidate_indices = set()
        for ngram in get_ngrams(new_norm, N_GRAM_SIZE):
            candidate_indices.update(self.index.get(ngram, set()))

        candidates = []
        for i in candidate_indices:
            norm_title = self.norm_titles[i]
            if not norm_title:
                continue

            ratio = fuzz.ratio(norm_title, new_norm) / 100.0

            # --- SUBSTRING BOOST ---
            # Boost score significantly if one is a substring of the other,
            # which is a strong signal for game titles with prefixes/suffixes.
            if norm_title in new_norm or new_norm in norm_title:
                ratio = max(ratio, 0.9)

            is_similar = ratio >= threshold
            # The aggressive normalization makes substring checks less reliable,
            # but direct ratio is now much more accurate.
            # We can still check for containment as a strong signal if needed,
            # but let's rely on the improved normalized ratio first.

            if is_similar:
                candidates.append((self.cached_titles[i], ratio))

        return candidates

async def find_similar_games_non_interactive(
    notion_client, new_title, cached_titles=None, threshold=0.85 # Increased threshold due to better normalization
):
    """Non-interactively finds similar games and returns candidates."""
    if not cached_titles or not isinstance(cached_titles[0], dict):
        cached_titles = await load_or_update_titles(notion_client)

    checker = SimilarityChecker(cached_titles)
    candidates = checker.filter_similar_titles(new_title, threshold)

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
        logging.warning(f"⚠️ 本地缓存读取失败: {e}")
    return []

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
        logging.info(f"🗂️ 游戏标题缓存成功写入，条目数: {len(valid_titles)}")
    except Exception as e:
        logging.error(f"❌ 缓存写入失败: {e}")

def hash_titles(data):
    items = sorted(
        f"{item.get("id")}:{item.get("title")}"
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
            logging.info("🔧 Notion 游戏标题有更新，重新缓存...")
            save_cache(remote_data)
            return remote_data
        return local_data
    except Exception as e:
        logging.warning(f"⚠️ 校验缓存失败，尝试从 Notion 拉取: {e}")
        try:
            remote_data = await notion_client.get_all_game_titles()
            save_cache(remote_data)
            return remote_data
        except Exception as e2:
            logging.error(f"❌ 无法连接 Notion，仅使用旧缓存: {e2}")
            return load_cache_quick()

async def remove_invalid_pages(candidates, cached_titles, notion_client):
    updated_cache = list(cached_titles)
    valid_candidates = []
    changed = False

    tasks = [notion_client.check_page_exists(item.get("id")) for item, score in candidates]
    results = await asyncio.gather(*tasks)

    for (item, score), exists in zip(candidates, results):
        page_id = item.get("id")
        if page_id and exists:
            valid_candidates.append((item, score))
        else:
            logging.warning(f"⚠️ 已失效页面：{item.get('title')}，从缓存移除")
            updated_cache = [x for x in updated_cache if x.get("id") != page_id]
            changed = True
    return valid_candidates, updated_cache, changed

async def check_existing_similar_games(
    notion_client, new_title, cached_titles=None, threshold=0.85 # Increased threshold
):
    logging.info("🔍 正在检查是否有可能重复的游戏...")

    if not cached_titles or not isinstance(cached_titles[0], dict):
        cached_titles = await load_or_update_titles(notion_client)

    checker = SimilarityChecker(cached_titles)
    candidates = checker.filter_similar_titles(new_title, threshold)

    valid_candidates, updated_cache, changed = await remove_invalid_pages(
        candidates, cached_titles, notion_client
    )

    if changed:
        save_cache(updated_cache)
        cached_titles = updated_cache

    notion_results = await notion_client.search_game(new_title)
    if notion_results:
        logging.warning(
            f"⚠️ Notion 实时搜索发现已有同名游戏：{notion_client.get_page_title(notion_results[0]) or '[未知标题]'}"
        )
        existing_page_data = {"id": notion_results[0]["id"], "title": new_title}
        valid_candidates = [
            (p, s) for p, s in valid_candidates if p["id"] != existing_page_data["id"]
        ]
        valid_candidates.insert(0, (existing_page_data, 1.0))

    if not valid_candidates:
        logging.info("✅ 没有发现重复游戏，将创建新条目。")
        return True, cached_titles, "create", None

    def _interactive_selection():
        logging.warning("⚠️ 检测到可能重复的游戏：")
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
        logging.info("🔍 已选择跳过。")
        return False, cached_titles, "skip", None
    elif choice == "c":
        confirm_check = await notion_client.search_game(new_title)
        if confirm_check:
            logging.warning("⚠️ 注意：你选择了强制新建，但Notion中已存在完全同名的游戏，自动转为更新。")
            return True, cached_titles, "update", confirm_check[0].get("id")
        else:
            logging.info("✅ 确认创建为新游戏。")
            return True, cached_titles, "create", None
    else:  # 默认为 u
        selected_id = sorted_candidates[0][0].get("id")
        logging.info(f"🔍 已选择更新游戏：{sorted_candidates[0][0].get('title')}")
        return True, cached_titles, "update", selected_id

# Restored original implementation of get_close_matches_with_ratio
def get_close_matches_with_ratio(query, candidates, limit=3, threshold=0.6):
    """Finds close matches, giving a strong boost to substring matches."""
    if not query or not candidates:
        return []

    scored_candidates = []
    # Do not normalize here, compare raw strings as the original logic intended
    norm_query = unicodedata.normalize("NFKC", query).lower()

    for cand in candidates:
        norm_cand = unicodedata.normalize("NFKC", cand).lower()

        ratio = fuzz.ratio(norm_query, norm_cand) / 100.0

        # Boost score significantly if one is a substring of the other
        if norm_query.startswith(norm_cand) or norm_cand.startswith(norm_query):
            ratio = max(ratio, 0.9)
        elif norm_cand in norm_query:
            ratio = max(ratio, 0.8)

        if ratio >= threshold:
            scored_candidates.append((cand, ratio))

    scored_candidates.sort(key=lambda x: (-x[1], x[0]))

    return [cand for cand, score in scored_candidates[:limit]]
