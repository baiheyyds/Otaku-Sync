import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json

from notion_client import Client

from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN, STATS_DB_ID

# ✅ 添加 cache 文件夹路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, "brand_latest_cache.json")

notion = Client(auth=NOTION_TOKEN)


# ========== 基础工具 ==========
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========== 获取游戏数据 ==========
def get_all_games():
    print("📥 获取所有游戏记录...")
    results = []
    start_cursor = None
    while True:
        response = notion.databases.query(
            database_id=GAME_DB_ID, page_size=100, **({"start_cursor": start_cursor} if start_cursor else {})
        )
        results.extend(response["results"])
        if not response.get("has_more"):
            break
        start_cursor = response.get("next_cursor")
    print(f"✅ 获取 {len(results)} 条游戏记录")
    return results


def get_safe_date(prop):
    if not isinstance(prop, dict):
        return None
    date_obj = prop.get("date")
    if isinstance(date_obj, dict):
        return date_obj.get("start")
    return None


def get_latest_game_data(games):
    brand_latest = {}
    latest_clear = None
    latest_release = None
    duration_map = {}

    for game in games:
        props = game.get("properties", {})
        title_blocks = props.get("游戏名称", {}).get("title", [])
        if not title_blocks:
            continue
        title = title_blocks[0].get("plain_text")

        clear_date = get_safe_date(props.get("通关时间"))
        release_date = get_safe_date(props.get("发售时间"))
        brand_relations = props.get("游戏厂商", {}).get("relation", [])

        duration = props.get("游玩时长（小时）", {}).get("number")
        if duration is not None:
            duration_map[title] = duration

        if release_date and (not latest_release or release_date > latest_release.get("date", "")):
            latest_release = {"title": title, "date": release_date}
        if clear_date and (not latest_clear or clear_date > latest_clear.get("date", "")):
            latest_clear = {"title": title, "date": clear_date}

        if clear_date and brand_relations:
            brand_id = brand_relations[0].get("id")
            if not brand_id:
                continue
            existing = brand_latest.get(brand_id)
            if not existing or clear_date > (existing.get("通关时间") or ""):
                brand_latest[brand_id] = {"title": title, "通关时间": clear_date}

    return brand_latest, latest_clear, latest_release, duration_map


# ========== 品牌信息更新 ==========
def update_brands(brand_map, cache):
    to_update = {brand_id: info for brand_id, info in brand_map.items() if cache.get(brand_id) != info["title"]}

    if not to_update:
        print("⚡ 所有厂商通关记录均为最新，无需更新")
        return cache

    print(f"🚀 正在更新 {len(to_update)} 个品牌...")

    updated = 0
    for brand_id, info in to_update.items():
        try:
            brand_page = notion.pages.retrieve(brand_id)
            current_title = brand_page["properties"].get("最近通关作品", {}).get("rich_text", [])
            current_text = current_title[0]["plain_text"] if current_title else ""
            if current_text == info["title"]:
                continue

            notion.pages.update(
                page_id=brand_id,
                properties={"最近通关作品": {"rich_text": [{"type": "text", "text": {"content": info["title"]}}]}},
            )
            print(f"✅ 更新：{info['title']} → 厂商 {brand_id}")
            cache[brand_id] = info["title"]
            updated += 1
        except Exception as e:
            print(f"❌ 更新失败：{brand_id}，错误：{e}")

    print(f"✨ 本次共更新了 {updated} 个品牌记录")
    return cache


def print_cache_hit_rate(brand_map, cache):
    total = len(brand_map)
    unchanged = sum(1 for k in brand_map if cache.get(k) == brand_map[k]["title"])
    print(f"📊 品牌缓存命中率：{unchanged}/{total}（{round(unchanged/total*100, 2)}%）")


def update_statistics_page(clear, release, all_games, duration_map):
    try:
        response = notion.databases.query(
            database_id=STATS_DB_ID, filter={"property": "类型", "select": {"equals": "通关统计"}}, page_size=1
        )
        if not response["results"]:
            print("⚠️ 未找到名称为「通关统计」的统计页面")
            return

        page_id = response["results"][0]["id"]
        properties = {}

        if clear:
            properties["最新通关游戏"] = {"rich_text": [{"type": "text", "text": {"content": clear["title"]}}]}
            duration = duration_map.get(clear["title"])
            if duration is not None:
                properties["最新通关用时"] = {"rich_text": [{"type": "text", "text": {"content": f"{duration} 小时"}}]}

        if release:
            properties["最新发售作品"] = {"rich_text": [{"type": "text", "text": {"content": release["title"]}}]}

        notion.pages.update(page_id=page_id, properties=properties)
        print(
            f"📊 更新统计页成功：「最新通关游戏」= {clear['title'] if clear else '无'}，"
            f"「最新发售作品」= {release['title'] if release else '无'}，"
            f"「最新通关用时」= {f'{duration} 小时' if clear and duration_map.get(clear['title']) else '无'}"
        )
    except Exception as e:
        print(f"❌ 更新统计页失败：{e}")


# ========== 主程序 ==========
if __name__ == "__main__":
    cache = load_cache()
    all_games = get_all_games()

    brand_latest_map, latest_clear, latest_release, duration_map = get_latest_game_data(all_games)
    print_cache_hit_rate(brand_latest_map, cache)
    new_cache = update_brands(brand_latest_map, cache)
    save_cache(new_cache)
    update_statistics_page(latest_clear, latest_release, all_games, duration_map)
