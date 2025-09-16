# scripts/auto_tag_completer.py
import asyncio
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.dlsite_client import DlsiteClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.driver_factory import driver_factory
from core.interaction import ConsoleInteractionProvider
from utils import logger
from utils.tag_manager import TagManager


async def get_tags_from_dlsite(dlsite_client: DlsiteClient, url: str) -> list:
    try:
        detail = await dlsite_client.get_game_detail(url)
        return detail.get("标签", [])
    except Exception as e:
        logger.error(f"❌ 获取 DLsite 标签失败: {e}")
        return []


async def get_tags_from_ggbase(ggbases_client: GGBasesClient, url: str) -> list:
    try:
        if not ggbases_client.has_driver():
            logger.warn("GGBasesClient 的 Selenium driver 未设置，跳过 GGBases 标签获取。")
            return []
        info = await ggbases_client.get_info_by_url_with_selenium(url)
        return info.get("标签", [])
    except Exception as e:
        logger.error(f"❌ 获取 GGBases 标签失败: {e}")
        return []


async def complete_missing_tags(
    notion_client: NotionClient,
    dlsite_client: DlsiteClient,
    ggbases_client: GGBasesClient,
    tag_manager: TagManager,
):
    """为 Notion 中缺少标签的游戏批量补全标签。"""
    logger.info("🛠️ 开始批量补全标签...")

    query_url = f"https://api.notion.com/v1/databases/{GAME_DB_ID}/query"
    payload = {"filter": {"property": FIELDS["tags"], "multi_select": {"is_empty": True}}}
    results = await notion_client._request("POST", query_url, payload)
    if not results or not results.get("results"):
        logger.info("✅ 没有需要补全标签的游戏。")
        return

    games = results.get("results", [])
    total = len(games)
    logger.info(f"找到 {total} 个需要补全标签的游戏。 সন")

    for idx, page in enumerate(games, start=1):
        props = page["properties"]
        title = notion_client.get_page_title(page)
        logger.info(f"\n🕵️‍♂️ 处理游戏 {idx}/{total}：{title}")

        dlsite_url = props.get(FIELDS["dlsite_link"], {}).get("url")
        ggbases_url = props.get(FIELDS["resource_link"], {}).get("url")

        raw_dlsite_tags, raw_ggbase_tags = [], []
        if dlsite_url:
            raw_dlsite_tags = await get_tags_from_dlsite(dlsite_client, dlsite_url)
        if ggbases_url:
            raw_ggbase_tags = await get_tags_from_ggbase(ggbases_client, ggbases_url)

        if not raw_dlsite_tags and not raw_ggbase_tags:
            logger.warn("🚫 未能从任何来源获取到标签。")
            continue

        logger.info("调用标签管理器处理标签...")
        final_tags = await tag_manager.process_tags(
            dlsite_tags=raw_dlsite_tags, fanza_tags=[], ggbases_tags=raw_ggbase_tags
        )

        if not final_tags:
            logger.warn("🚫 经过处理后，没有可用的最终标签。")
            continue

        logger.success(f"整理出最终标签: {final_tags}")

        update_payload = {
            "properties": {FIELDS["tags"]: {"multi_select": [{"name": tag} for tag in final_tags]}}
        }
        update_url = f"https://api.notion.com/v1/pages/{page['id']}"
        await notion_client._request("PATCH", update_url, update_payload)
        logger.success(f"✅ 成功为 '{title}' 更新了 {len(final_tags)} 个标签。 সন")
        await asyncio.sleep(0.5)


async def main():
    """脚本独立运行时的入口函数。"""
    driver_factory.start_background_creation(["ggbases_driver"])
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as async_client:
            interaction_provider = ConsoleInteractionProvider()
            tag_manager = TagManager(interaction_provider)

            notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
            dlsite_client = DlsiteClient(async_client)
            ggbases_client = GGBasesClient(async_client)

            driver = await driver_factory.get_driver("ggbases_driver")
            if driver:
                ggbases_client.set_driver(driver)
            else:
                logger.error("未能创建 GGBases 的 Selenium Driver，部分功能将受限。 সন")

            # Build context dictionary
            context = {
                "notion": notion_client,
                "dlsite": dlsite_client,
                "ggbases": ggbases_client,
                "tag_manager": tag_manager,
            }
            await complete_missing_tags(context)
            # 保存所有在交互过程中可能发生的变动
            tag_manager.save_all_maps()

    finally:
        await driver_factory.close_all_drivers()


if __name__ == "__main__":
    asyncio.run(main())
