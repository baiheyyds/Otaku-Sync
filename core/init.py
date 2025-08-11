# core/init.py
import asyncio

import httpx

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.getchu_client import GetchuClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager  # <--- 核心改动
from utils import logger
from utils.driver import create_driver
from utils.similarity_check import hash_titles, load_cache_quick, save_cache


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

    async_client = httpx.AsyncClient(timeout=20, follow_redirects=True, http2=True)

    dlsite_driver_task = asyncio.to_thread(create_driver)
    ggbases_driver_task = asyncio.to_thread(create_driver)
    dlsite_driver, ggbases_driver = await asyncio.gather(dlsite_driver_task, ggbases_driver_task)
    logger.system("专属 Selenium 驱动池已创建。")

    bgm_mapper = BangumiMappingManager()
    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)

    # --- 核心改动：初始化 Schema 管理器 ---
    # --- 核心改动：初始化 Schema 管理器 ---
    schema_manager = NotionSchemaManager(notion)
    # 【关键修复】确保游戏、角色、厂商三个数据库的结构都被加载
    await asyncio.gather(
        schema_manager.initialize_schema(GAME_DB_ID, "游戏数据库"),
        schema_manager.initialize_schema(CHARACTER_DB_ID, "角色数据库"),
        schema_manager.initialize_schema(BRAND_DB_ID, "厂商数据库"),
    )

    # 将 Schema 管理器注入 BangumiClient
    bangumi = BangumiClient(notion, bgm_mapper, schema_manager, async_client)
    # --- 核心改动结束 ---

    dlsite = DlsiteClient(async_client)
    getchu = GetchuClient(async_client)
    ggbases = GGBasesClient(async_client)

    dlsite.set_driver(dlsite_driver)
    ggbases.set_driver(ggbases_driver)

    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()
    cached_titles = await asyncio.to_thread(load_cache_quick)
    logger.cache(f"本地缓存游戏条目数: {len(cached_titles)}")
    asyncio.create_task(update_cache_background(notion, cached_titles))

    return {
        "dlsite_driver": dlsite_driver,
        "ggbases_driver": ggbases_driver,
        "async_client": async_client,
        "notion": notion,
        "bangumi": bangumi,
        "dlsite": dlsite,
        "getchu": getchu,
        "ggbases": ggbases,
        "brand_cache": brand_cache,
        "brand_extra_info_cache": brand_extra_info_cache,
        "cached_titles": cached_titles,
    }


async def close_context(context: dict):
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
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
