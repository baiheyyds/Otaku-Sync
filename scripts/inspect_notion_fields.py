# scripts/inspect_notion_fields.py
import asyncio
import logging
import os
import sys

import httpx

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from clients.notion_client import NotionClient
from config import config_token


def list_database_ids_from_config() -> dict:
    """从 config.config_token 中提取所有以 _DB_ID 结尾的变量。"""
    db_ids = {}
    for key in dir(config_token):
        if key.endswith("_DB_ID"):
            db_ids[key] = getattr(config_token, key)
    return db_ids


async def inspect_database(notion_client: NotionClient, db_id: str, db_name: str):
    """
    获取并打印指定数据库的字段信息。

    :param notion_client: 初始化好的 NotionClient 实例。
    :param db_id: 要查询的数据库 ID。
    :param db_name: 数据库的变量名，用于显示。
    """
    logging.info(f"\n🔍 正在查询 {db_name} ({db_id[-5:]})...")
    schema = await notion_client.get_database_schema(db_id)

    if not schema:
        logging.error(f"❌ 获取数据库 {db_name} 的结构失败。")
        return

    properties = schema.get("properties", {})
    logging.info("\n📘 数据库字段信息如下：\n")
    for name, prop in properties.items():
        prop_type = prop.get("type", "未知")
        logging.info(f"🔹 字段名: {name}")
        logging.info(f"   类型: {prop_type}")
        logging.info("-" * 40)


async def main():
    """脚本主入口，处理用户交互。"""
    db_map = list_database_ids_from_config()
    if not db_map:
        logging.error("❌ 在 config/config_token.py 中未找到任何 _DB_ID。")
        return

    print("📂 请选择要查看的数据库：\n")
    options = list(db_map.items())
    for idx, (name, _) in enumerate(options, 1):
        print(f"[{idx}] {name}")

    try:
        choice = input("\n请输入编号：").strip()
        if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
            print("❌ 输入无效")
            return
    except (EOFError, KeyboardInterrupt):
        print("\n操作取消。")
        return

    db_key, db_id = options[int(choice) - 1]

    async with httpx.AsyncClient(timeout=20) as async_client:
        # NotionClient 初始化需要所有 DB ID，即使只用一个
        notion_client = NotionClient(
            token=config_token.NOTION_TOKEN,
            game_db_id=config_token.GAME_DB_ID,  # Placeholder
            brand_db_id=config_token.BRAND_DB_ID,  # Placeholder
            client=async_client,
        )
        await inspect_database(notion_client, db_id, db_key)


if __name__ == "__main__":
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()
    asyncio.run(main())
