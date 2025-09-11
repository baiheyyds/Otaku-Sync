# core/init.py
import asyncio

import httpx

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.fanza_client import FanzaClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager
from utils.tag_manager import TagManager
from utils import logger
from utils.similarity_check import hash_titles, load_cache_quick, save_cache
from .data_manager import data_manager # <-- 1. 导入 DataManager 实例


async def update_cache_background(notion_client, local_cache):
    try:
        logger.system("正在后台刷新查重缓存...")
        await asyncio.sleep(0.1)
        remote_data = await notion_client.get_all_game_titles()
        local_hash = hash_titles(local_cache)
        remote_hash = hash_titles(remote_data)
        if local_hash != remote_hash:
            if remote_data:
                save_cache(remote_data)
            else:
                logger.warn("拉取到的远程缓存为空，跳过保存以避免清空本地缓存")
        else:
            logger.info("游戏标题缓存已是最新")
    except Exception as e:
        logger.warn(f"后台更新缓存失败: {e}")


async def init_context():
    logger.system("启动程序...")

    transport = httpx.AsyncHTTPTransport(retries=3, http2=True)
    async_client = httpx.AsyncClient(transport=transport, timeout=20, follow_redirects=True)

    bgm_mapper = BangumiMappingManager()
    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
    schema_manager = NotionSchemaManager(notion)

    db_configs = {
        GAME_DB_ID: "游戏数据库",
        CHARACTER_DB_ID: "角色数据库",
        BRAND_DB_ID: "厂商数据库",
    }
    await schema_manager.load_all_schemas(db_configs)

    bangumi = BangumiClient(notion, bgm_mapper, schema_manager, async_client)
    dlsite = DlsiteClient(async_client)
    fanza = FanzaClient(async_client)
    ggbases = GGBasesClient(async_client)
    tag_manager = TagManager()

    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()
    cached_titles = await asyncio.to_thread(load_cache_quick)
    logger.cache(f"本地缓存游戏条目数: {len(cached_titles)}")
    asyncio.create_task(update_cache_background(notion, cached_titles))

    return {
        "dlsite_driver": None,
        "ggbases_driver": None,
        "async_client": async_client,
        "notion": notion,
        "bangumi": bangumi,
        "dlsite": dlsite,
        "fanza": fanza,
        "ggbases": ggbases,
        "brand_cache": brand_cache,
        "brand_extra_info_cache": brand_extra_info_cache,
        "cached_titles": cached_titles,
        "schema_manager": schema_manager,
        "tag_manager": tag_manager,
        "data_manager": data_manager,  # <-- 2. 将实例添加到上下文中
    }


async def close_context(context: dict):
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if context.get("async_client"):
        await context["async_client"].aclose()
        logger.system("HTTP 客户端已关闭。")

    close_tasks = []
    if context.get("dlsite_driver"):
        close_tasks.append(asyncio.to_thread(context["dlsite_driver"].quit))
    if context.get("ggbases_driver"):
        close_tasks.append(asyncio.to_thread(context["ggbases_driver"].quit))

    if close_tasks:
        await asyncio.gather(*close_tasks)
        logger.system("Selenium 驱动池已关闭。")

    logger.system("正在保存所有缓存数据...")
    if context.get("brand_cache") and context.get("brand_extra_info_cache"):
        context["brand_cache"].save_cache(context["brand_extra_info_cache"])

    if context.get("schema_manager"):
        context["schema_manager"].save_schemas_to_cache()

    # --- [修复 2] --- #
    if context.get("tag_manager"):
        context["tag_manager"].save_all_maps()
    # --- [修复结束] --- #
