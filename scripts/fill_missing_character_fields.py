# scripts/fill_missing_character_fields.py
import asyncio
import logging
import os
import re
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


def extract_bangumi_char_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"/character/(\d+)", url)
    return m.group(1) if m else None


def is_update_needed(properties: dict) -> bool:
    """检查角色页面是否缺少需要补充的字段。"""
    # 要检查的字段列表
    fields_to_check = [
        FIELDS["character_bwh"],
        FIELDS["character_height"],
        FIELDS["character_birthday"],
        FIELDS["character_blood_type"],
        FIELDS["character_gender"],
    ]
    # 检查任一字段是否不存在或其内容为空
    for field in fields_to_check:
        prop = properties.get(field)
        if not prop:
            return True  # 属性本身不存在
        prop_type = prop.get("type")
        if prop_type == "rich_text" and not prop.get("rich_text"):
            return True
        if prop_type == "select" and not prop.get("select"):
            return True
    return False


async def fill_missing_character_fields(
    context: dict
):
    """遍历角色数据库，为缺少特定字段的角色从Bangumi补充信息。"""
    notion_client = context["notion"]
    bangumi_client = context["bangumi"]
    
    logging.info("开始扫描角色数据库以补充缺失字段...")
    all_characters = await notion_client.get_all_pages_from_db(CHARACTER_DB_ID)
    if not all_characters:
        logging.warning("角色数据库中没有任何条目。")
        return

    total = len(all_characters)
    logging.info(f"共拉取到 {total} 个角色条目，开始检查和更新。")

    updated_count = 0
    skipped_count = 0

    for idx, page in enumerate(all_characters, 1):
        page_id = page["id"]
        props = page.get("properties", {})
        char_name = notion_client.get_page_title(page)

        logging.info(f"\n[{idx}/{total}] 正在处理角色: {char_name}")

        if not is_update_needed(props):
            logging.info("✅ 所有关键字段已填写，跳过。")
            skipped_count += 1
            continue

        detail_url = props.get(FIELDS["character_url"], {}).get("url")
        char_id = extract_bangumi_char_id(detail_url)

        if not char_id:
            logging.warning(f"⚠️ 无法从URL中提取Bangumi角色ID，跳过: {detail_url}")
            skipped_count += 1
            continue

        logging.info(f"正在从Bangumi获取角色 {char_id} 的详细信息...")
        char_data_to_update = await bangumi_client.fetch_and_prepare_character_data(char_id)

        if not char_data_to_update:
            logging.error(f"❌ 从Bangumi获取角色 {char_id} 的信息失败。")
            skipped_count += 1
            continue

        # create_or_update_character 会处理页面的创建或更新逻辑
        result_id = await bangumi_client.create_or_update_character(char_data_to_update, set())
        if result_id:
            updated_count += 1
        else:
            skipped_count += 1

        await asyncio.sleep(1)  # 尊重Bangumi API的速率限制

    logging.info("\n--- 扫描完成 ---")
    logging.info(f"✅ 成功更新或确认了 {updated_count} 个角色。")
    logging.info(f"⏩ 跳过了 {skipped_count} 个无需更新或无法处理的角色。")


async def main():
    """脚本独立运行时的入口函数。"""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as async_client:
        # 1. 初始化所有必要的组件
        interaction_provider = ConsoleInteractionProvider()
        notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
        schema_manager = NotionSchemaManager(notion_client)
        await schema_manager.load_all_schemas({CHARACTER_DB_ID: "角色数据库"})
        bgm_mapper = BangumiMappingManager(interaction_provider)

        bangumi_client = BangumiClient(
            notion=notion_client,
            mapper=bgm_mapper,
            schema=schema_manager,
            client=async_client,
            interaction_provider=interaction_provider,
        )

        # 2. 执行核心逻辑
        context = {
            "notion": notion_client,
            "bangumi": bangumi_client,
        }
        await fill_missing_character_fields(context)

        # 3. 保存可能发生的映射变更
        bgm_mapper.save_mappings()


if __name__ == "__main__":
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()
    asyncio.run(main())
