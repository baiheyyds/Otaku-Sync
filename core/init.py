# core/init.py
import asyncio
from .context_factory import create_shared_context, create_loop_specific_context
from .interaction import ConsoleInteractionProvider
from utils import logger

async def init_context():
    """Initializes the context for the command-line application."""
    logger.system("启动程序...")
    interaction_provider = ConsoleInteractionProvider()
    shared_context = create_shared_context()
    loop_specific_context = await create_loop_specific_context(shared_context, interaction_provider)
    return {**shared_context, **loop_specific_context}

async def close_context(context: dict):
    # Close loop-specific resources
    if context.get("async_client"):
        await context["async_client"].aclose()
        logger.system("HTTP 客户端已关闭。")

    # Close shared resources
    if context.get("driver_factory"):
        await context["driver_factory"].close_all_drivers()

    # Save all caches
    logger.system("正在保存所有缓存数据...")
    if context.get("brand_cache") and context.get("brand_extra_info_cache"):
        context["brand_cache"].save_cache(context["brand_extra_info_cache"])

    if context.get("schema_manager"):
        context["schema_manager"].save_schemas_to_cache()

    if context.get("tag_manager"):
        context["tag_manager"].save_all_maps()
