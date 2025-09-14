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
from core.schema_manager import NotionSchemaManager
from utils.tag_manager import TagManager
from utils import logger
from utils.similarity_check import hash_titles, load_cache_quick, save_cache
from .data_manager import data_manager
from .driver_factory import driver_factory


def create_shared_context():
    """Creates context with objects that are shared across the application's lifetime."""
    logger.system("正在初始化共享应用上下文 (缓存、驱动工厂等)...")
    driver_factory.start_background_creation(["dlsite_driver", "ggbases_driver"])
    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()
    tag_manager = TagManager()
    cached_titles = load_cache_quick()
    logger.cache(f"本地缓存游戏条目数: {len(cached_titles)}")

    return {
        "driver_factory": driver_factory,
        "brand_cache": brand_cache,
        "brand_extra_info_cache": brand_extra_info_cache,
        "cached_titles": cached_titles,
        "tag_manager": tag_manager,
        "data_manager": data_manager,
    }

async def create_loop_specific_context(shared_context: dict, interaction_provider: InteractionProvider):
    """Creates context with objects that are specific to a single event loop (e.g. http clients)."""
    transport = httpx.AsyncHTTPTransport(retries=3, http2=True)
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
    bangumi = BangumiClient(notion, bgm_mapper, schema_manager, async_client)
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

async def create_context(interaction_provider: InteractionProvider):
    """Creates and initializes all the clients and managers for the application."""
    shared_context = create_shared_context()
    loop_specific_context = await create_loop_specific_context(shared_context, interaction_provider)
    return {**shared_context, **loop_specific_context}
