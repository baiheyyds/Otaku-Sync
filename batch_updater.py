# batch_updater.py
import asyncio
import re
import sys
from tqdm.asyncio import tqdm

from core.init import init_context, close_context
from utils import logger
from config.config_token import GAME_DB_ID, BRAND_DB_ID, CHARACTER_DB_ID
from config.config_fields import FIELDS

# --- 可配置项 ---
CONCURRENCY_LIMIT = 8

DB_CONFIG = {
    "games": {"id": GAME_DB_ID, "name": "游戏数据库", "bangumi_url_prop": FIELDS["bangumi_url"]},
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

# [新增] 反向映射，用于在猴子补丁中根据ID查找名字
DB_ID_TO_KEY_MAP = {v["id"]: k for k, v in DB_CONFIG.items()}


def extract_id_from_url(url: str) -> str | None:
    if not url:
        return None
    match = re.search(r"/(subject|person|character)/(\d+)", url)
    return match.group(2) if match else None


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
                    bangumi_data = await bangumi_client.fetch_game(bangumi_id)
                    if not bangumi_data:
                        raise ValueError("从Bangumi获取游戏数据失败")

                    schema = context["schema_manager"].get_schema(config["id"])
                    await notion_client.create_or_update_game(
                        properties_schema=schema, page_id=page_id, **bangumi_data
                    )

                elif db_key == "brands":
                    # [关键修复] 使用 bangumi_id 直接获取数据，而不是搜索
                    bangumi_data = await bangumi_client.fetch_person_by_id(bangumi_id)
                    if not bangumi_data:
                        logger.warn(
                            f"无法通过ID {bangumi_id} 获取品牌 '{page_title}' 的信息，已跳过。"
                        )
                        return

                    brand_name = page_title
                    # [关键修复] 传入已知的 page_id，避免重复搜索，提高效率
                    await notion_client.create_or_update_brand(
                        brand_name, page_id=page_id, **bangumi_data
                    )

                elif db_key == "characters":
                    char_data = await bangumi_client.fetch_and_prepare_character_data(bangumi_id)
                    if not char_data:
                        raise ValueError(f"准备角色 {bangumi_id} 数据失败")

                    warned_keys = set()
                    await bangumi_client.create_or_update_character(char_data, warned_keys)

        except Exception as e:
            logger.error(f"处理页面 '{page_title}' ({page_id}) 时出错: {e}")


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


def get_user_choice():
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
                return db_options
            else:
                print("无效的数字，请重新输入。")
        except ValueError:
            print("无效输入，请输入数字或 'q'。")


async def main():
    dbs_to_update = get_user_choice()
    if not dbs_to_update:
        logger.info("用户选择退出。")
        return

    context = await init_context()

    # [已修复] 猴子补丁现在能正确工作了
    # 我们用一个包装函数临时替换原始的 handle_new_key
    from core.mapping_manager import BangumiMappingManager

    original_handle_new_key = BangumiMappingManager.handle_new_key

    async def new_handle_new_key_wrapper(
        self, bangumi_key, bangumi_value, bangumi_url, notion_client, schema_manager, target_db_id
    ):
        result = await original_handle_new_key(
            self,
            bangumi_key,
            bangumi_value,
            bangumi_url,
            notion_client,
            schema_manager,
            target_db_id,
        )
        if result:
            schema = schema_manager.get_schema(target_db_id)
            # 只有当创建了一个schema中没有的属性时才刷新
            if result not in schema:
                logger.system(f"检测到新属性 '{result}' 已创建，正在刷新数据库结构...")
                db_key = DB_ID_TO_KEY_MAP.get(target_db_id)
                if db_key:
                    await schema_manager.initialize_schema(target_db_id, DB_CONFIG[db_key]["name"])
                    logger.success("数据库结构缓存已刷新！")
        return result

    BangumiMappingManager.handle_new_key = new_handle_new_key_wrapper

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
