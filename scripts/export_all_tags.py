# scripts/export_all_tags.py
import asyncio
import os
import sys

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from utils import logger


async def export_all_tags(context: dict) -> list[str]:
    """
    从 Notion 游戏数据库中导出所有使用过的标签。

    :param context: 包含 notion_client 的应用上下文。
    :return: 一个包含所有唯一标签的排序列表。
    """
    notion_client = context["notion"]
    tag_field_name = FIELDS.get("tags", "标签")
    logger.info(f"📥 正在从 Notion 获取所有游戏记录以提取 '{tag_field_name}' 标签...")

    pages = await notion_client.get_all_pages_from_db(GAME_DB_ID)
    if not pages:
        logger.warn("⚠️ 未获取到任何游戏页面。")
        return []

    logger.info(f"✅ 获取到 {len(pages)} 条记录，开始解析标签。")

    tag_set = set()
    for page in pages:
        try:
            props = page.get("properties", {})
            tags_prop = props.get(tag_field_name, {})
            if tags_prop.get("type") == "multi_select":
                tags = tags_prop.get("multi_select", [])
                tag_set.update(tag["name"] for tag in tags)
        except Exception as e:
            logger.printf("处理页面 %s 时出错: %s", page.get('id'), e)
            continue  # 跳过无法解析的条目

    return sorted(list(tag_set))


async def main():
    """脚本独立运行时的入口函数。"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as async_client:
        # NotionClient 初始化需要 BRAND_DB_ID，即使此脚本不直接使用
        notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)

        tags = await export_all_tags(notion_client)

        if tags:
            output_filename = "all_tags.txt"
            with open(output_filename, "w", encoding="utf-8") as f:
                for tag in tags:
                    f.write(tag + "\n")
            logger.system(f"✅ 成功将 {len(tags)} 个唯一标签写入到 {output_filename}")
        else:
            logger.warn("🤷‍♀️ 未提取到任何标签。")


if __name__ == "__main__":
    asyncio.run(main())