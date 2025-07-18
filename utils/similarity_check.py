# utils/similarity_check.py
# 该模块用于检查游戏标题的相似性，避免重复创建游戏条目
import difflib
import unicodedata
import re
from pathlib import Path
import json
import sys

def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", "", text)
    return text

def get_cache_path():
    # 取当前执行脚本（main.py）所在目录，保证缓存在 main.py 同目录下的 cache 文件夹
    base_dir = Path(sys.argv[0]).resolve().parent
    cache_dir = base_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "game_titles_cache.json"

def load_cache():
    path = get_cache_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_cache(titles):
    valid_titles = [t for t in titles if t.get("title") and t.get("id")]
    path = get_cache_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(valid_titles, f, ensure_ascii=False, indent=2)

def check_existing_similar_games(notion_client, new_title, cached_titles=None, threshold=0.78):
    print("🔍 正在检查是否有可能重复的游戏...")

    # 缓存为空或格式为纯字符串时，拉取 Notion 数据
    if cached_titles is None or not cached_titles or (len(cached_titles) > 0 and isinstance(cached_titles[0], str)):
        print("📥 正在从 Notion 拉取全部游戏标题...")
        all_game_data = notion_client.get_all_game_titles()
    else:
        all_game_data = cached_titles

    new_norm = normalize(new_title)
    candidates = []
    for item in all_game_data:
        # 可能 item 是 dict，也可能是字符串，兼容处理
        title = item["title"] if isinstance(item, dict) else item
        ratio = difflib.SequenceMatcher(None, normalize(title), new_norm).ratio()
        if ratio >= threshold:
            candidates.append((item, ratio))

    if candidates:
        print("⚠️ 检测到可能重复的游戏：")
        for item, score in sorted(candidates, key=lambda x: x[1], reverse=True):
            title = item["title"] if isinstance(item, dict) else item
            print(f"  - {title}（相似度：{score:.2f}）")

        print("请选择操作：")
        print("1. ✅ 创建为新游戏")
        print("2. 🔄 更新已有游戏（覆盖）")
        print("3. ⛔ 跳过该游戏")

        while True:
            choice = input("请输入数字 1/2/3 并回车：").strip()
            if choice in {"1", "2", "3"}:
                break

        if choice == "3":
            return False, all_game_data, None, None
        elif choice == "2":
            if isinstance(candidates[0][0], dict) and "id" in candidates[0][0]:
                return True, all_game_data, "update", candidates[0][0]["id"]
            else:
                print("⚠️ 无法获取页面ID（缓存数据无 id），将跳过该条目")
                return False, all_game_data, None, None
        else:
            return True, all_game_data, "create", None
    else:
        print("✅ 没有发现重复游戏")
        return True, all_game_data, "create", None
