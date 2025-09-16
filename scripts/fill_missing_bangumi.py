# scripts/fill_missing_bangumi.py
import asyncio
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.bangumi_client import BangumiClient
from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.interaction import ConsoleInteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager
from utils import logger


async def get_games_missing_bangumi(notion_client: NotionClient) -> list:
    """获取所有缺少 Bangumi 链接的游戏页面。"""
    logger.info("正在从 Notion 查询缺少 Bangumi 链接的游戏...")
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


async def fill_missing_bangumi_links(
    notion_client: NotionClient, bangumi_client: BangumiClient
):
    """为缺少 Bangumi 链接的游戏查找、匹配并填充信息。"""
    games_to_process = await get_games_missing_bangumi(notion_client)
    if not games_to_process:
        logger.info("✅ 所有游戏都已包含 Bangumi 链接，无需处理。")
        return

    total = len(games_to_process)
    logger.info(f"找到 {total} 个缺少 Bangumi 链接的游戏，开始处理。")
    unmatched_titles = []

    for idx, game_page in enumerate(games_to_process, 1):
        page_id = game_page["id"]
        title = notion_client.get_page_title(game_page)
        logger.info(f"\n[{idx}/{total}] 正在处理游戏: {title}")

        try:
            subject_id = await bangumi_client.search_and_select_bangumi_id(title)

            if not subject_id:
                logger.warn(f"❌ 未能为 '{title}' 找到匹配的 Bangumi 条目，已跳过。")
                unmatched_titles.append(title)
                continue

            logger.success(f"匹配成功！Bangumi Subject ID: {subject_id}")
            logger.info("开始获取角色信息并更新 Notion 页面...")

            await bangumi_client.create_or_link_characters(page_id, subject_id)

            logger.success(f"✅ 游戏 '{title}' 的 Bangumi 信息和角色关联已全部处理完毕。")

        except Exception as e:
            logger.error(f"处理游戏 '{title}' 时发生未知异常: {e}", exc_info=True)
            unmatched_titles.append(title)
        
        finally:
            await asyncio.sleep(1.5) # 尊重 API 速率限制

    if unmatched_titles:
        logger.warn("\n--- 未匹配的游戏 ---")
        for unmatched_title in unmatched_titles:
            logger.warn(f"- {unmatched_title}")
        with open("unmatched_games.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(unmatched_titles))
        logger.info("未匹配的游戏列表已保存到 unmatched_games.txt")


async def main():
    """脚本独立运行时的入口函数。"""
    context = {}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, http2=True) as async_client:
            # 1. 初始化所有必要的组件
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
            
            context = {
                "notion": notion_client,
                "bangumi": bangumi_client,
                # ... other clients if needed by other functions
            }

            # 2. 执行核心逻辑
            await fill_missing_bangumi_links(context)

            # 3. 保存可能发生的映射变更
            bgm_mapper.save_mappings()
    except Exception as e:
        logger.error(f"脚本主函数运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
