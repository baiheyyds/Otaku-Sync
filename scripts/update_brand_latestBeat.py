# scripts/update_brand_latestBeat.py
import asyncio
import json
import logging
import os
import sys

import httpx
from tqdm.asyncio import tqdm_asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN, STATS_DB_ID

# 缓存文件路径
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, "brand_latest_cache.json")


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _process_game_data(games: list) -> tuple:
    """从游戏页面列表中处理和提取统计数据。"""
    brand_latest = {}
    latest_clear = None
    latest_release = None
    duration_map = {}

    for game in games:
        props = game.get("properties", {})

        def get_prop_value(prop_name, value_type):
            prop = props.get(prop_name, {})
            if value_type == "title":
                return prop.get("title", [{}])[0].get("plain_text")
            if value_type == "date":
                date_obj = prop.get("date")
                return date_obj.get("start") if isinstance(date_obj, dict) else None
            if value_type == "relation":
                return prop.get("relation", [])
            if value_type == "number":
                return prop.get("number")
            return None

        title = get_prop_value(FIELDS["game_name"], "title")
        if not title:
            continue

        clear_date = get_prop_value(FIELDS["clear_date"], "date")
        release_date = get_prop_value(FIELDS["release_date"], "date")
        brand_relations = get_prop_value(FIELDS["brand_relation"], "relation")
        duration = get_prop_value(FIELDS["playtime"], "number")

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


async def _update_brand_pages(notion_client: NotionClient, brand_map: dict, cache: dict) -> dict:
    """根据最新的通关游戏数据并发更新品牌页面。"""
    to_update = {
        brand_id: info
        for brand_id, info in brand_map.items()
        if cache.get(brand_id) != info["title"]
    }

    if not to_update:
        logging.info("⚡ 所有厂商通关记录均为最新，无需更新。")
        return cache

    logging.info(f"🚀 检测到 {len(to_update)} 个品牌需要更新，开始并发处理...")

    # Notion API 速率限制信号量，允许3个并发请求
    notion_semaphore = asyncio.Semaphore(3)
    updated_cache = cache.copy()

    async def update_single_brand(brand_id, info):
        async with notion_semaphore:
            try:
                payload = {
                    "properties": {
                        FIELDS["brand_latest_cleared_game"]: {
                            "rich_text": [
                                {"type": "text", "text": {"content": info["title"]}}
                            ]
                        }
                    }
                }
                await notion_client._request(
                    "PATCH", f"https://api.notion.com/v1/pages/{brand_id}", payload
                )
                updated_cache[brand_id] = info["title"]
                return brand_id, info["title"], None  # Success
            except Exception as e:
                return brand_id, info["title"], e  # Failure

    tasks = [update_single_brand(brand_id, info) for brand_id, info in to_update.items()]

    results = await tqdm_asyncio.gather(*tasks, desc="更新品牌页面")

    updated_count = 0
    for brand_id, title, error in results:
        if error:
            logging.error(f"  ❌ 更新品牌 {brand_id} ({title}) 失败: {error}")
        else:
            updated_count += 1
            # 成功日志可以省略，因为进度条已经提供了反馈

    logging.info(f"✨ 本次共更新了 {updated_count} 个品牌记录。")
    return updated_cache


async def _update_statistics_page(notion_client: NotionClient, clear: dict, release: dict, duration_map: dict):
    """更新总览统计页面。"""
    try:
        pages = await notion_client.get_all_pages_from_db(STATS_DB_ID)
        stat_page = next((p for p in pages if notion_client.get_page_title(p) == "通关统计"), None)

        if not stat_page:
            logging.warning("⚠️ 未找到标题为「通关统计」的页面，无法更新统计数据。")
            return

        page_id = stat_page["id"]
        properties = {}

        if clear:
            properties[FIELDS["stats_latest_cleared_game"]] = {"rich_text": [{"type": "text", "text": {"content": clear["title"]}}]}
            duration = duration_map.get(clear["title"])
            if duration is not None:
                properties[FIELDS["latest_cleared_playtime"]] = {
                    "rich_text": [{"type": "text", "text": {"content": f"{duration} 小时"}}]
                }

        if release:
            properties[FIELDS["latest_released_game"]] = {"rich_text": [{"type": "text", "text": {"content": release["title"]}}]}

        await notion_client._request("PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"properties": properties})
        logging.info("📊 成功更新统计页。")

    except Exception as e:
        logging.error(f"❌ 更新统计页失败: {e}")


async def update_brand_and_game_stats(context: dict):
    notion_client = context["notion"]
    """完整执行更新品牌最新通关和全局游戏统计的整个流程。"""
    logging.info("🚀 开始执行品牌及游戏统计数据更新流程...")
    cache = load_cache()

    logging.info("📥 正在获取所有游戏记录...")
    all_games = await notion_client.get_all_pages_from_db(GAME_DB_ID)
    if not all_games:
        logging.error("未能获取任何游戏数据，脚本终止。")
        return
    logging.info(f"✅ 获取到 {len(all_games)} 条游戏记录。")

    brand_latest_map, latest_clear, latest_release, duration_map = _process_game_data(all_games)

    total = len(brand_latest_map)
    unchanged = sum(1 for k in brand_latest_map if cache.get(k) == brand_latest_map[k]["title"])
    if total > 0:
        logging.info(f"📊 品牌缓存命中率: {unchanged}/{total} ({round(unchanged/total*100, 2)}%)")

    new_cache = await _update_brand_pages(notion_client, brand_latest_map, cache)
    save_cache(new_cache)

    await _update_statistics_page(notion_client, latest_clear, latest_release, duration_map)
    logging.info("流程执行完毕。")


async def main():
    """脚本独立运行时的入口函数。"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as async_client:
        notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
        context = {"notion": notion_client}
        await update_brand_and_game_stats(context)


if __name__ == "__main__":
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()
    asyncio.run(main())
