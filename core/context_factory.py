# core/context_factory.py
import asyncio

import httpx

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.fanza_client import FanzaClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.interaction import InteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.name_splitter import NameSplitter
from core.schema_manager import NotionSchemaManager
from utils import logger
from utils.similarity_check import hash_titles, load_cache_quick, save_cache
from utils.tag_manager import TagManager

from .data_manager import data_manager
from .driver_factory import driver_factory


def create_shared_context():
    """Creates context with objects that are shared across the application's lifetime."""
    logger.system("正在初始化共享应用上下文 (缓存、管理器、驱动工厂等)...")
    driver_factory.start_background_creation(["dlsite_driver", "ggbases_driver"])

    # 管理器现在是共享的
    tag_manager = TagManager()
    name_splitter = NameSplitter()

    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()
    cached_titles = load_cache_quick()
    logger.cache(f"本地缓存游戏条目数: {len(cached_titles)}")

    return {
        "driver_factory": driver_factory,
        "brand_cache": brand_cache,
        "brand_extra_info_cache": brand_extra_info_cache,
        "cached_titles": cached_titles,
        "data_manager": data_manager,
        "tag_manager": tag_manager,
        "name_splitter": name_splitter,
    }


async def create_loop_specific_context(
    shared_context: dict, interaction_provider: InteractionProvider
):
    """Creates context with objects that are specific to a single event loop (e.g. http clients)."""
    # transport = httpx.AsyncHTTPTransport(retries=3, http2=True) # The client-level retry is removed in favor of manual retry in background task
    transport = httpx.AsyncHTTPTransport(http2=True)
    async_client = httpx.AsyncClient(transport=transport, timeout=20, follow_redirects=True)

    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
    schema_manager = NotionSchemaManager(notion)
    db_configs = {
        GAME_DB_ID: "游戏数据库",
        CHARACTER_DB_ID: "角色数据库",
        BRAND_DB_ID: "厂商数据库",
    }
    await schema_manager.load_all_schemas(db_configs)

    bgm_mapper = BangumiMappingManager(interaction_provider)
    bangumi = BangumiClient(notion, bgm_mapper, schema_manager, async_client, interaction_provider)
    dlsite = DlsiteClient(async_client)
    fanza = FanzaClient(async_client)
    ggbases = GGBasesClient(async_client)

    # Update cached_titles in the background
    asyncio.create_task(update_cache_background(notion, shared_context["cached_titles"]))

    return {
        "async_client": async_client,
        "notion": notion,
        "schema_manager": schema_manager,
        "bangumi": bangumi,
        "dlsite": dlsite,
        "fanza": fanza,
        "ggbases": ggbases,
        "interaction_provider": interaction_provider,
    }


async def update_cache_background(notion_client, local_cache):
    """后台更新查重缓存，带有网络错误重试逻辑。"""
    for attempt in range(3):
        try:
            if attempt == 0:
                logger.system("正在后台刷新查重缓存...")
            else:
                logger.system(f"后台缓存刷新重试... ({attempt + 1}/3)")

            await asyncio.sleep(1)
            remote_data = await notion_client.get_all_game_titles()

            if remote_data is None:
                logger.error("获取远程缓存时发生不可恢复的API错误，后台更新中止。")
                return

            local_hash = hash_titles(local_cache)
            remote_hash = hash_titles(remote_data)
            if local_hash != remote_hash:
                save_cache(remote_data)
                logger.info("后台查重缓存已成功更新。")
            else:
                logger.info("游戏标题缓存已是最新。")
            return  # Exit function on success

        except httpx.RequestError as e:
            logger.warn(f"后台缓存更新时发生网络错误 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))  # 5s, 10s wait
            continue  # continue to the next attempt
        except Exception as e:
            logger.error(f"处理后台缓存更新时发生未知严重错误: {e}")
            return  # Abort on unknown errors

    logger.error("后台缓存更新任务在多次网络尝试后彻底失败。")


async def create_context(interaction_provider: InteractionProvider):
    """Creates and initializes all the clients and managers for the application."""
    shared_context = create_shared_context()
    loop_specific_context = await create_loop_specific_context(shared_context, interaction_provider)
    return {**shared_context, **loop_specific_context}
