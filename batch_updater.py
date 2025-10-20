# batch_updater.py
import asyncio
import logging
import re
from tqdm import tqdm
from typing import List, Dict, Any

from core.init import init_context, close_context
from config.config_token import GAME_DB_ID, BRAND_DB_ID, CHARACTER_DB_ID
from config.config_fields import FIELDS

# --- 可配置项 ---
# 这现在是每一批次并发处理的数量
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

DB_ID_TO_KEY_MAP = {v["id"]: k for k, v in DB_CONFIG.items()}


def extract_id_from_url(url: str) -> str | None:
    if not url:
        return None
    match = re.search(r"/(subject|person|character)/(\d+)", url)
    return match.group(2) if match else None


def chunker(seq, size):
    """将一个列表分割成指定大小的块"""
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))


async def check_if_dirty(context, bangumi_data: Dict[str, Any], db_id: str) -> bool:
    """
    预检查从Bangumi获取的数据是否包含任何未被映射的新属性。
    这是避免不必要锁定的关键。
    """
    mapper = context["bangumi"].mapper
    schema = context["schema_manager"].get_schema(db_id)
    if not schema:
        return True  # 如果没有schema，保守地认为所有都是新属性

    # Bangumi数据中的所有潜在key
    keys_to_check = set(bangumi_data.keys())

    # _process_infobox 会创建组合key，我们也需要模拟检查它们
    # (这是一个简化的模拟，但已能覆盖绝大多数情况)
    if "infobox" in bangumi_data and isinstance(bangumi_data["infobox"], list):
        for item in bangumi_data["infobox"]:
            key = item.get("key")
            value = item.get("value")
            if not key:
                continue

            keys_to_check.add(key)
            if isinstance(value, list):
                for sub_item in value:
                    if isinstance(sub_item, dict) and "k" in sub_item:
                        sub_key = sub_item.get("k")
                        keys_to_check.add(f"{key}-{sub_key}")
                        if key == "链接":
                            keys_to_check.add(sub_key)

    for key in keys_to_check:
        if not mapper.get_notion_prop(key, db_id):
            return True  # 发现一个未映射的key，标记为dirty

    return False


async def preprocess_item(context, page: Dict[str, Any], db_key: str) -> Dict[str, Any] | None:
    """
    第一阶段：并发获取数据并进行预处理。
    """
    bangumi_client = context["bangumi"]
    config = DB_CONFIG[db_key]

    try:
        bangumi_url_prop = page.get("properties", {}).get(config["bangumi_url_prop"], {})
        bangumi_url = bangumi_url_prop.get("url")
        bangumi_id = extract_id_from_url(bangumi_url)

        if not bangumi_id:
            return None

        bangumi_data = {}
        if db_key == "games":
            bangumi_data = await bangumi_client.fetch_game(bangumi_id)
        elif db_key == "brands":
            bangumi_data = await bangumi_client.fetch_person_by_id(bangumi_id)
        elif db_key == "characters":
            # 对于角色，我们需要更完整的数据结构用于写入
            bangumi_data = await bangumi_client.fetch_and_prepare_character_data(bangumi_id)

        if not bangumi_data:
            return None

        # is_dirty = await check_if_dirty(context, bangumi_data, config["id"])
        # 简化逻辑：我们假设任何需要交互的步骤都应该串行化。
        # fetch_and_prepare_character_data 内部已经调用了 _process_infobox,
        # 我们在这里再次调用来检查新属性，而不是重新实现检查逻辑。
        temp_processed = await bangumi_client._process_infobox(
            bangumi_data.get("infobox", []), config["id"], ""
        )
        is_dirty = any(
            prop not in context["schema_manager"].get_schema(config["id"])
            for prop in temp_processed.keys()
        )

        return {
            "page": page,
            "bangumi_data": bangumi_data,
            "is_dirty": is_dirty,  # 关键标记
        }
    except Exception as e:
        page_title = context["notion"].get_page_title(page)
        logging.warning(f"⚠️ 预处理 '{page_title}' 时失败: {e}")
        return None


async def write_item_to_notion(context, item_data: Dict[str, Any], db_key: str):
    """
    第二阶段：将预处理好的数据写入Notion。
    """
    notion_client = context["notion"]
    name_splitter = context["name_splitter"]
    interaction_provider = context["interaction_provider"]
    config = DB_CONFIG[db_key]
    page = item_data["page"]
    page_id = page["id"]
    page_title = notion_client.get_page_title(page)
    bangumi_data = item_data["bangumi_data"]

    try:
        if db_key == "games":
            schema = context["schema_manager"].get_schema(config["id"])
            
            # [关键修复] 在提交通知前，对需要分割的字段进行处理
            fields_to_split = ["剧本", "原画", "声优", "音乐", "作品形式"]
            for field in fields_to_split:
                if field in bangumi_data:
                    raw_values = bangumi_data[field]
                    if not isinstance(raw_values, list):
                        raw_values = [raw_values]
                    
                    processed_names = set()
                    for raw_item in raw_values:
                        split_results = await name_splitter.smart_split(raw_item, interaction_provider)
                        processed_names.update(split_results)
                    
                    bangumi_data[field] = sorted(list(processed_names))

            await notion_client.create_or_update_game(
                properties_schema=schema, page_id=page_id, **bangumi_data
            )
        elif db_key == "brands":
            await notion_client.create_or_update_brand(page_title, page_id=page_id, **bangumi_data)
        elif db_key == "characters":
            warned_keys = set()
            await context["bangumi"].create_or_update_character(bangumi_data, warned_keys)
    except Exception as e:
        logging.error(f"❌ 写入页面 '{page_title}' ({page_id}) 时出错: {e}")


async def batch_update(context, dbs_to_update: List[str]):
    interaction_lock = asyncio.Lock()
    notion_client = context["notion"]

    for db_key in dbs_to_update:
        config = DB_CONFIG[db_key]
        logging.info(f"🚀 开始处理 {config['name']}...")

        all_pages = await notion_client.get_all_pages_from_db(config["id"])
        if not all_pages:
            logging.warning(f"⚠️ {config['name']} 中没有找到任何页面。")
            continue

        logging.info(f"✅ 共找到 {len(all_pages)} 个条目，将以每批 {CONCURRENCY_LIMIT} 个并发处理...")

        # 使用tqdm包装分块器，以批次为单位显示进度
        for page_chunk in tqdm(
            list(chunker(all_pages, CONCURRENCY_LIMIT)), desc=f"更新 {config['name']}", unit="批"
        ):
            # --- 阶段一：并发获取和预处理 ---
            preprocess_tasks = [preprocess_item(context, page, db_key) for page in page_chunk]
            processed_items = await asyncio.gather(*preprocess_tasks)
            processed_items = [item for item in processed_items if item]  # 过滤掉失败的

            # --- 任务分离 ---
            clean_items = [item for item in processed_items if not item["is_dirty"]]
            dirty_items = [item for item in processed_items if item["is_dirty"]]

            # --- 阶段二(A)：并发写入“干净”的条目 ---
            if clean_items:
                write_clean_tasks = [
                    write_item_to_notion(context, item, db_key) for item in clean_items
                ]
                await asyncio.gather(*write_clean_tasks)

            # --- 阶段二(B)：串行写入“有问题”的条目以处理交互 ---
            if dirty_items:
                for item in dirty_items:
                    async with interaction_lock:
                        await write_item_to_notion(context, item, db_key)

        logging.info(f"✅ {config['name']} 处理完成！")


async def main():
    dbs_to_update = get_user_choice()
    if not dbs_to_update:
        logging.info("🔍 用户选择退出。")
        return

    context = await init_context()

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
        if result and result not in schema_manager.get_schema(target_db_id):
            logging.info(f"🔧 检测到新属性 '{result}' 已创建，正在刷新数据库结构...")
            db_key = DB_ID_TO_KEY_MAP.get(target_db_id)
            if db_key:
                await schema_manager.initialize_schema(target_db_id, DB_CONFIG[db_key]["name"])
                logging.info("✅ 数据库结构缓存已刷新！")
        return result

    BangumiMappingManager.handle_new_key = new_handle_new_key_wrapper

    try:
        await batch_update(context, dbs_to_update)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.warning("\n⚠️ 接收到中断信号，正在退出...")
    except Exception as e:
        logging.error(f"❌ 批量更新流程出现未捕获的严重错误: {e}")
    finally:
        logging.info("🔧 正在清理资源...")
        await close_context(context)
        context["brand_cache"].save_cache(context["brand_extra_info_cache"])
        logging.info("✅ 批量更新程序已安全退出。")


# get_user_choice() 和 __main__ 部分保持不变
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


if __name__ == "__main__":
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()
    asyncio.run(main())