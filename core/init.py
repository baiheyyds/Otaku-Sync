# core/init.py
import logging

from .context_factory import create_loop_specific_context, create_shared_context
from .driver_factory import driver_factory
from .interaction import ConsoleInteractionProvider


async def init_context():
    """Initializes the context for the command-line application."""
    logging.info("🚀 启动程序...")
    interaction_provider = ConsoleInteractionProvider()
    shared_context = create_shared_context()
    loop_specific_context = await create_loop_specific_context(shared_context, interaction_provider)
    return {**shared_context, **loop_specific_context}

async def close_context(context: dict):
    # Shutdown browser drivers first
    await driver_factory.shutdown_async()

    # Close loop-specific resources
    if context.get("async_client"):
        await context["async_client"].aclose()
        logging.info("🔧 HTTP 客户端已关闭。")

    # Save all caches and mappings
    logging.info("🔧 正在保存所有缓存和映射数据...")
    if context.get("brand_cache"):
        context["brand_cache"].save_cache()

    if context.get("schema_manager"):
        context["schema_manager"].save_schemas_to_cache()

    if context.get("tag_manager"):
        context["tag_manager"].save_all_maps()

    if context.get("brand_mapping_manager"):
        context["brand_mapping_manager"].save_mapping()

    if context.get("name_splitter"):
        context["name_splitter"].save_exceptions()
