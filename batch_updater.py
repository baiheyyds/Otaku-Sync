# batch_updater.py
import asyncio
import re
import sys
import argparse
from tqdm.asyncio import tqdm

from core.init import init_context, close_context
from utils import logger
from config.config_token import GAME_DB_ID, BRAND_DB_ID, CHARACTER_DB_ID
from config.config_fields import FIELDS
from core.mapping_manager import BangumiMappingManager  # <--- [修复] 导入

# --- 可配置项 ---
CONCURRENCY_LIMIT = 4

DB_CONFIG = {
    "games": {
        "id": GAME_DB_ID,
        "name": "游戏数据库",
        "bangumi_url_prop": FIELDS["bangumi_url"],
    },
    "brands": {
        "id": BRAND_DB_ID,
        "name": "厂商数据库",
        "bangumi_url_prop": FIELDS["brand_bangumi_url"],
    },
    "characters": {
        "id": CHARACTER_DB_ID,
        "name": "角色数据库",
        "bangumi_url_prop": FIELDS["character_url"],
    },
}

# --- 核心逻辑 ---


def extract_id_from_url(url: str) -> str | None:
    if not url:
        return None
    match = re.search(r"/(subject|person|character)/(\d+)", url)
    return match.group(2) if match else None


# [修复] 补上 handle_new_key 的模拟，以刷新 schema
original_handle_new_key = BangumiMappingManager.handle_new_key


async def new_handle_new_key(
    self, bangumi_key, bangumi_value, bangumi_url, notion_client, schema_manager, target_db_id
):
    """
    这是一个包装函数 (Monkey Patch)。
    它会调用原始的 handle_new_key 函数来处理用户交互。
    如果原始函数成功创建了一个新属性并返回了属性名，
    这个函数会立即刷新 schema_manager 中的缓存。
    """
    # 调用原始的、会弹出用户交互的函数
    result = await original_handle_new_key(
        self, bangumi_key, bangumi_value, bangumi_url, notion_client, schema_manager, target_db_id
    )

    # 如果用户在交互中确实创建了一个新属性 (result 不为 None)，则刷新缓存
    if result:
        # 检查这个返回的属性名是否真的是“新”的
        # （用户也可能选择映射到已有属性，那种情况无需刷新）
        schema = schema_manager.get_schema(target_db_id)
        if result not in schema:
            logger.system(f"检测到新属性 '{result}' 已创建，正在刷新数据库结构缓存...")
            db_name = DB_CONFIG.get(target_db_id, {}).get("name", "未知数据库")
            await schema_manager.initialize_schema(target_db_id, db_name)
            logger.success("数据库结构缓存已刷新！")

    return result


# --- 猴子补丁结束 ---


async def process_item(context, page, db_key, semaphore, interaction_lock):
    notion_client = context["notion"]
    bangumi_client = context["bangumi"]

    page_id = page["id"]
    page_title = notion_client.get_page_title(page)
    config = DB_CONFIG[db_key]

    async with semaphore:
        try:
            bangumi_url_prop = page.get("properties", {}).get(config["bangumi_url_prop"], {})
            bangumi_url = bangumi_url_prop.get("url")

            bangumi_id = extract_id_from_url(bangumi_url)
            if not bangumi_id:
                return

            async with interaction_lock:
                if db_key == "games":
                    # --- [核心修复] ---
                    # 1. 先执行可能触发 schema 变更的 bangumi 数据获取
                    bangumi_data = await bangumi_client.fetch_game(bangumi_id)
                    if not bangumi_data:
                        raise ValueError("从Bangumi获取游戏数据失败")

                    # 2. 在所有交互和 schema 变更完成后，再获取最新版本的 schema
                    schema = context["schema_manager"].get_schema(config["id"])

                    # 3. 使用最新的 schema 进行更新
                    await notion_client.create_or_update_game(
                        properties_schema=schema, page_id=page_id, **bangumi_data
                    )
                    # --- [修复结束] ---

                elif db_key == "brands":
                    brand_name = page_title
                    bangumi_data = await bangumi_client.fetch_brand_info_from_bangumi(brand_name)
                    if not bangumi_data:
                        return
                    await notion_client.create_or_update_brand(
                        brand_name, page_id=page_id, **bangumi_data
                    )

                elif db_key == "characters":
                    char_detail_url = f"https://api.bgm.tv/v0/characters/{bangumi_id}"
                    resp = await bangumi_client.client.get(
                        char_detail_url, headers=bangumi_client.headers
                    )
                    if resp.status_code != 200:
                        raise ValueError("无法获取角色详情")

                    detail = resp.json()
                    char_url = f"https://bangumi.tv/character/{detail['id']}"
                    infobox_data = await bangumi_client._process_infobox(
                        detail.get("infobox", []), CHARACTER_DB_ID, char_url
                    )

                    char_data_to_update = {
                        "name": detail.get("name"),
                        "aliases": [detail.get("name_cn")] if detail.get("name_cn") else [],
                        "avatar": detail.get("images", {}).get("large", ""),
                        "summary": detail.get("summary", "").strip(),
                        "url": char_url,
                    }
                    char_data_to_update.update(infobox_data)

                    warned_keys = set()
                    await bangumi_client.create_or_update_character(
                        char_data_to_update, warned_keys
                    )

        except Exception as e:
            logger.error(f"❌ 处理页面 '{page_title}' ({page_id}) 时出错: {e}")


async def batch_update(context, dbs_to_update):
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    interaction_lock = asyncio.Lock()
    notion_client = context["notion"]

    for db_key in dbs_to_update:
        config = DB_CONFIG[db_key]
        logger.step(f"开始处理 {config['name']}...")

        all_pages = await notion_client.get_all_pages_from_db(config["id"])
        if not all_pages:
            logger.warn(f"{config['name']} 中没有找到任何页面。")
            continue

        logger.info(f"共找到 {len(all_pages)} 个条目，将并发处理...")

        tasks = [
            process_item(context, page, db_key, semaphore, interaction_lock) for page in all_pages
        ]

        await tqdm.gather(*tasks, desc=f"更新 {config['name']}")

        logger.success(f"{config['name']} 处理完成！")


# [交互优化] 新的 get_user_choice 函数
def get_user_choice():
    """显示菜单并获取用户的选择。"""
    print("\n请选择要批量更新的数据库：\n")
    db_options = list(DB_CONFIG.keys())
    for i, key in enumerate(db_options):
        print(f"  [{i+1}] {DB_CONFIG[key]['name']}")
    print(f"  [{len(db_options) + 1}] 更新以上所有数据库")
    print("  [q] 退出\n")

    while True:
        choice = input("请输入数字选项并回车: ").strip().lower()
        if choice == "q":
            return None

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(db_options):
                return [db_options[choice_num - 1]]
            elif choice_num == len(db_options) + 1:
                return db_options  # 返回所有
            else:
                print("无效的数字，请重新输入。")
        except ValueError:
            print("无效输入，请输入数字或 'q'。")


async def main():
    # [交互优化] 使用新的菜单函数
    dbs_to_update = get_user_choice()
    if not dbs_to_update:
        logger.info("用户选择退出。")
        return

    context = await init_context()

    # --- [关键修复] 猴子补丁 ---
    # 在运行时，用我们带刷新逻辑的新函数，临时替换掉原始的 handle_new_key 函数
    BangumiMappingManager.handle_new_key = new_handle_new_key
    # --- 补丁结束 ---

    try:
        await batch_update(context, dbs_to_update)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warn("\n接收到中断信号，正在退出...")
    except Exception as e:
        logger.error(f"批量更新流程出现未捕获的严重错误: {e}")
    finally:
        logger.system("正在清理资源...")
        await close_context(context)
        context["brand_cache"].save_cache(context["brand_extra_info_cache"])
        logger.system("批量更新程序已安全退出。")


if __name__ == "__main__":
    asyncio.run(main())
