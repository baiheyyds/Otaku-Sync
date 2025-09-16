# scripts/extract_brands.py
import asyncio
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from utils import logger


async def export_brand_names(notion_client: NotionClient) -> list[str]:
    """
    从 Notion 数据库中导出所有品牌名称。

    :param notion_client: 初始化好的 NotionClient 实例。
    :return: 一个包含所有品牌名称的排序列表。
    """
    logger.info("🔍 正在从 Notion 读取所有品牌...")
    all_brand_pages = await notion_client.get_all_pages_from_db(BRAND_DB_ID)

    if not all_brand_pages:
        logger.warn("⚠️ 未能从 Notion 获取到任何品牌信息。")
        return []

    brand_names = {
        notion_client.get_page_title(page)
        for page in all_brand_pages
        if notion_client.get_page_title(page)
    }

    logger.success(f"✅ 成功提取到 {len(brand_names)} 个唯一的品牌名称。")
    return sorted(list(brand_names))


async def main():
    """脚本独立运行时的入口函数。"""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as async_client:
        # 注意：GAME_DB_ID 在此脚本中不是必需的，但 NotionClient 初始化需要它
        notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)

        context = {"notion": notion_client}
        brand_names = await export_brand_names(context)

        if brand_names:
            output_filename = "brand_names.txt"
            with open(output_filename, "w", encoding="utf-8") as f:
                for name in brand_names:
                    f.write(name + "\n")
            logger.system(f"✅ 已将 {len(brand_names)} 个品牌名写入到 {output_filename}")


if __name__ == "__main__":
    asyncio.run(main())