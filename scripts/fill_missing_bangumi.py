# scripts/fill_missing_bangumi.py
import asyncio
import logging
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asyncio import Semaphore
from clients.bangumi_client import BangumiClient
from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.interaction import ConsoleInteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager
from tqdm.asyncio import tqdm_asyncio


async def get_games_missing_bangumi(notion_client: NotionClient) -> list:
    """获取所有缺少 Bangumi 链接的游戏页面。"""
    logging.info("🔍 正在从 Notion 查询缺少 Bangumi 链接的游戏...")
    query_url = f"https://api.notion.com/v1/databases/{GAME_DB_ID}/query"
    payload = {"filter": {"property": FIELDS["bangumi_url"], "url": {"is_empty": True}}}
    
    all_games = []
    next_cursor = None
    while True:
        if next_cursor:
            payload["start_cursor"] = next_cursor
        resp = await notion_client._request("POST", query_url, payload)
        if not resp:
            break
        results = resp.get("results", [])
        all_games.extend(results)
        if not resp.get("has_more"):
            break
        next_cursor = resp.get("next_cursor")
        
    return all_games


async def process_single_game(
    game_page: dict, notion_client: NotionClient, bangumi_client: BangumiClient
) -> tuple[str, bool]:
    """处理单个游戏的核心逻辑，作为一个独立的原子操作。"""
    page_id = game_page["id"]
    title = notion_client.get_page_title(game_page)
    logging.info(f"\n正在处理游戏: {title}")

    try:
        subject_id = await bangumi_client.search_and_select_bangumi_id(title)

        if not subject_id:
            logging.warning(f"❌ 未能为 '{title}' 找到匹配的 Bangumi 条目，已跳过。")
            return title, False

        logging.info(f"✅ 匹配成功！Bangumi Subject ID: {subject_id}")
        logging.info("开始获取角色信息并更新 Notion 页面...")

        await bangumi_client.create_or_link_characters(page_id, subject_id)

        logging.info(f"✅ 游戏 '{title}' 的 Bangumi 信息和角色关联已全部处理完毕。")
        return title, True

    except Exception as e:
        logging.error(f"处理游戏 '{title}' 时发生未知异常: {e}", exc_info=True)
        return title, False
    finally:
        # 仍然保留一个小的延时，作为最后的保险，使整体请求更平滑
        await asyncio.sleep(1.5)


async def fill_missing_bangumi_links(context: dict):
    """为缺少 Bangumi 链接的游戏查找、匹配并填充信息。"""
    notion_client = context["notion"]
    bangumi_client = context["bangumi"]

    games_to_process = await get_games_missing_bangumi(notion_client)
    if not games_to_process:
        logging.info("✅ 所有游戏都已包含 Bangumi 链接，无需处理。")
        return

    total = len(games_to_process)
    logging.info(f"找到 {total} 个缺少 Bangumi 链接的游戏，开始并发处理。")

    # 在脚本内部创建信号量，限制并发处理的游戏数量
    semaphore = Semaphore(3)

    async def process_with_semaphore(game_page):
        async with semaphore:
            return await process_single_game(game_page, notion_client, bangumi_client)

    tasks = [process_with_semaphore(gp) for gp in games_to_process]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    unmatched_titles = []
    for result in results:
        if isinstance(result, Exception):
            logging.error(f"任务执行中发生严重异常: {result}")
            continue
        title, success = result
        if not success:
            unmatched_titles.append(title)

    if unmatched_titles:
        logging.warning("\n--- 未匹配的游戏 ---")
        for unmatched_title in unmatched_titles:
            logging.warning(f"- {unmatched_title}")
        with open("unmatched_games.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(unmatched_titles))
        logging.info("未匹配的游戏列表已保存到 unmatched_games.txt")


async def main():
    """脚本独立运行时的入口函数。"""
    context = {}
    bgm_mapper = None
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=True) as async_client:
            interaction_provider = ConsoleInteractionProvider()
            notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
            schema_manager = NotionSchemaManager(notion_client)
            await schema_manager.load_all_schemas(
                {GAME_DB_ID: "游戏数据库", CHARACTER_DB_ID: "角色数据库"}
            )
            bgm_mapper = BangumiMappingManager(interaction_provider)

            bangumi_client = BangumiClient(
                notion=notion_client,
                mapper=bgm_mapper,
                schema=schema_manager,
                client=async_client,
                interaction_provider=interaction_provider,
            )

            context = {"notion": notion_client, "bangumi": bangumi_client}
            await fill_missing_bangumi_links(context)

    except Exception as e:
        logging.error(f"脚本主函数运行出错: {e}", exc_info=True)
    finally:
        if bgm_mapper:
            bgm_mapper.save_mappings()


if __name__ == "__main__":
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()
    asyncio.run(main())