# core/init.py
import asyncio
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

    # Save all caches and mappings concurrently in background threads
    logging.info("🔧 正在并发保存所有缓存和映射数据...")

    save_tasks = []

    # Helper functions to safely call save methods
    def save_brand_cache():
        if context.get("brand_cache"):
            context["brand_cache"].save_cache()

    def save_schema_cache():
        if context.get("schema_manager"):
            context["schema_manager"].save_schemas_to_cache()

    def save_tag_maps():
        if context.get("tag_manager"):
            context["tag_manager"].save_all_maps()

    def save_brand_mapping():
        if context.get("brand_mapping_manager"):
            context["brand_mapping_manager"].save_mapping()

    def save_name_splitter_exceptions():
        if context.get("name_splitter"):
            context["name_splitter"].save_exceptions()

    # List of functions to run in threads
    sync_saves = [
        save_brand_cache,
        save_schema_cache,
        save_tag_maps,
        save_brand_mapping,
        save_name_splitter_exceptions,
    ]

    # Create tasks to run these functions in the default thread pool executor
    save_tasks = [asyncio.to_thread(func) for func in sync_saves]

    # Wait for all save operations to complete
    results = await asyncio.gather(*save_tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logging.error(f"❌ 保存数据时发生错误 ({sync_saves[i].__name__}): {result}")

    logging.info("✅ 所有数据保存任务已完成。")
