# scripts/replace_and_clean_tags.py
import asyncio
import os
import sys
from collections import Counter

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from mapping.tag_replace_map import tag_replace_map
from utils import logger


async def replace_tags_in_pages(notion_client: NotionClient, dry_run: bool = True) -> set[str]:
    """
    遍历所有游戏页面，根据映射替换标签，并返回所有使用中的标签。
    """
    tag_field = FIELDS["tags"]
    pages = await notion_client.get_all_pages_from_db(GAME_DB_ID)
    total_pages = len(pages)
    modified_pages = 0
    deleted_tag_counter = Counter()
    used_tags = set()

    logger.info(f"✅ 共读取 {total_pages} 条游戏记录，开始检查标签替换...")

    for page in pages:
        props = page.get("properties", {})
        tag_prop = props.get(tag_field)
        if not tag_prop or tag_prop.get("type") != "multi_select":
            continue

        current_tags = tag_prop.get("multi_select", [])
        current_names = [t["name"] for t in current_tags]

        # 替换标签
        new_names_set = set(tag_replace_map.get(name, name) for name in current_names)
        new_names_list = sorted(list(new_names_set))
        used_tags.update(new_names_list)  # 使用新标签更新“已用标签”集合

        changed = set(current_names) != new_names_set

        if changed:
            modified_pages += 1
            replaced = [name for name in current_names if name in tag_replace_map]
            deleted_tag_counter.update(replaced)

            logger.info(f"🟡 修改页面: {page['id']}")
            logger.info(f"   原标签: {current_names}")
            logger.info(f"   新标签: {new_names_list}")

            if not dry_run:
                payload = {
                    "properties": {
                        tag_field: {"multi_select": [{"name": name} for name in new_names_list]}
                    }
                }
                await notion_client._request("PATCH", f"https://api.notion.com/v1/pages/{page['id']}", payload)
                logger.info("   ✅ 已更新\n")
            else:
                logger.info("   🔍 [dry-run] 模拟更新\n")

    logger.system("\n🎯 标签替换统计结果")
    logger.info(f"📄 总页面数: {total_pages}")
    logger.info(f"📝 被修改的页面数: {modified_pages}")
    logger.info(f"❌ 被替换的旧标签总数: {sum(deleted_tag_counter.values())}")
    if deleted_tag_counter:
        logger.info("📊 替换明细:")
        for tag, count in deleted_tag_counter.items():
            logger.info(f"   - {tag}: {count} 次")

    return used_tags


async def find_and_report_unused_tags(notion_client: NotionClient, used_tags: set[str]):
    """
    获取数据库中定义的所有标签，与在用标签对比，找出未使用的并报告。
    """
    logger.info("\n🧹 正在检测未使用标签...")
    tag_field_name = FIELDS["tags"]

    db_schema = await notion_client.get_database_schema(GAME_DB_ID)
    if not db_schema:
        logger.error("❌ 无法获取数据库结构，无法检测未使用标签。\n")
        return

    tag_field = db_schema.get("properties", {}).get(tag_field_name)
    if not tag_field or tag_field.get("type") != "multi_select":
        logger.error(f"❌ 找不到 '{tag_field_name}' 字段定义，或字段不是 multi_select 类型。\n")
        return

    current_options = tag_field.get("multi_select", {}).get("options", [])
    all_defined_tags = {opt["name"] for opt in current_options}
    unused_tags = sorted(list(all_defined_tags - used_tags))

    if not unused_tags:
        logger.success("✅ 所有已定义的标签都有使用，无需清理。\n")
        return

    logger.warn(f"🧹 共发现 {len(unused_tags)} 个未使用的标签:")
    for tag in unused_tags:
        logger.warn(f"   - {tag}")

    output_filename = "unused_tags.txt"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(unused_tags))
    logger.system(f"\n📄 未使用标签已保存至 {output_filename} 文件。请在 Notion 中手动删除这些标签。\n")


async def run_replace_and_clean_tags(context: dict, dry_run: bool = True):
    """脚本主入口"""
    notion_client = context["notion"]
    if dry_run:
        logger.system("** [Dry Run] 模式，不会对 Notion 进行任何实际修改 **\n")

    # 步骤1: 替换标签并获取所有在用标签
    used_tags = await replace_tags_in_pages(notion_client, dry_run)

    # 步骤2: 基于在用标签查找并报告未使用的标签
    await find_and_report_unused_tags(notion_client, used_tags)


async def main(dry_run: bool = True):
    """脚本独立运行时的入口函数。"""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as async_client:
        context = {
            "notion": NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
        }
        await run_replace_and_clean_tags(context, dry_run)


if __name__ == "__main__":
    # 设置为 False 以实际执行更新
    # asyncio.run(main(dry_run=False))
    asyncio.run(main(dry_run=True))