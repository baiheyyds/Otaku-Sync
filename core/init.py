# core/init.py
import asyncio
import threading

import httpx

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.getchu_client import GetchuClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from utils import logger
from utils.similarity_check import hash_titles, load_cache_quick, save_cache


async def update_cache_background(notion_client, local_cache):
    """
    在同一个事件循环中以后台任务方式运行的异步缓存更新。
    这避免了创建新线程和新事件循环带来的I/O冲突。
    """
    try:
        logger.system("正在后台刷新查重缓存...")
        # 等待短暂时间，确保主流程的初始化信息先打印出来
        await asyncio.sleep(0.1)
        remote_data = await notion_client.get_all_game_titles()

        local_hash = hash_titles(local_cache)
        remote_hash = hash_titles(remote_data)
        if local_hash != remote_hash:
            if remote_data:
                save_cache(remote_data)
                logger.success("后台缓存刷新成功")
            else:
                logger.warn("拉取到的远程缓存为空，跳过保存以避免清空本地缓存")
        else:
            logger.info("游戏标题缓存已是最新")
    except Exception as e:
        logger.warn(f"后台更新缓存失败: {e}")


async def init_context():
    logger.system("启动程序...")

    async_client = httpx.AsyncClient(timeout=20, follow_redirects=True, http2=True)

    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
    bangumi = BangumiClient(notion, async_client)
    dlsite = DlsiteClient(async_client)
    getchu = GetchuClient(async_client)
    ggbases = GGBasesClient(async_client)

    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()

    cached_titles = await asyncio.to_thread(load_cache_quick)
    logger.cache(f"本地缓存游戏条目数: {len(cached_titles)}")

    # 使用 asyncio.create_task 以非阻塞方式启动后台任务
    # 这是处理并发后台任务的 asyncio 原生方式
    asyncio.create_task(update_cache_background(notion, cached_titles))

    return {
        "driver": None,
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
    """优雅地关闭所有资源"""
    # 确保所有挂起的任务有机会完成或被取消
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)

    if context.get("async_client"):
        await context["async_client"].aclose()
        logger.system("HTTP 客户端已关闭。")
    if context.get("driver"):
        await asyncio.to_thread(context["driver"].quit)
        logger.system("浏览器驱动已关闭。")
