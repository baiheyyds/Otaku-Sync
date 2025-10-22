import asyncio
import logging
import os
import sys
import time

import httpx

# 将项目根目录添加到 Python 路径中，以便能够导入其他模块
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from asyncio import Semaphore

from clients.bangumi_client import BangumiClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.interaction import ConsoleInteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager


async def process_brand_page(
    brand_page: dict,
    notion_client: NotionClient,
    bangumi_client: BangumiClient,
    bgm_semaphore: Semaphore,
):
    """处理单个品牌页面的更新逻辑"""
    brand_name = notion_client.get_page_title(brand_page)
    page_id = brand_page.get("id")
    if not brand_name:
        logging.warning(f"⚠️ 跳过一个没有名称的品牌页面 (Page ID: {page_id})")
        return

    # 使用信号量来限制对 Bangumi API 的并发访问
    async with bgm_semaphore:
        # 每次请求前都短暂 sleep，模拟更真实的用户行为，进一步降低被拒绝的风险
        await asyncio.sleep(1.2)
        bangumi_info = await bangumi_client.fetch_brand_info_from_bangumi(brand_name)

    if not bangumi_info:
        logging.warning(f"⚠️ 在 Bangumi 上未能找到 '{brand_name}' 的匹配信息，跳过更新。")
        return

    success = await notion_client.create_or_update_brand(
        brand_name=brand_name, page_id=page_id, **bangumi_info
    )

    if success:
        logging.info(f"✅ 品牌 '{brand_name}' 的信息已成功更新。")
    else:
        logging.error(f"❌ 品牌 '{brand_name}' 的信息更新失败。")


async def main(context: dict, progress_callback=None):
    """主执行函数"""
    logging.info("🚀 启动品牌信息批量更新脚本...")

    # 1. 初始化所有核心组件
    notion_client = context["notion"]
    bangumi_client = context["bangumi"]
    schema_manager = context["schema_manager"]

    # Bangumi API 速率限制信号量，允许1个并发
    bgm_semaphore = Semaphore(1)

    start_time = time.time()

    try:
        # 2. 预加载 Schema
        await schema_manager.initialize_schema(BRAND_DB_ID, "厂商数据库")
        await schema_manager.initialize_schema(CHARACTER_DB_ID, "角色数据库")

        # 3. 从 Notion 获取所有品牌页面
        logging.info("正在从 Notion 获取所有品牌页面...")
        all_brand_pages = await notion_client.get_all_pages_from_db(BRAND_DB_ID)
        if not all_brand_pages:
            logging.error("未能从 Notion 获取到任何品牌信息，脚本终止。")
            return

        total_brands = len(all_brand_pages)
        logging.info(f"✅ 成功获取到 {total_brands} 个品牌，开始并发更新...")

        if progress_callback:
            progress_callback("start", total=total_brands)

        # 4. 创建所有并发任务
        tasks = []
        for i, page in enumerate(all_brand_pages):
            tasks.append(process_brand_page(
                page, notion_client, bangumi_client, bgm_semaphore
            ))

        # 5. 逐个执行任务并更新进度
        for i, task in enumerate(asyncio.as_completed(tasks)):
            try:
                await task
                current_count = i + 1
                if progress_callback:
                    elapsed = time.time() - start_time
                    progress_callback("update", current=current_count, text=f"更新品牌信息: {current_count}/{total_brands}", elapsed_time_string=f"耗时: {elapsed:.2f}秒")
            except Exception as e:
                logging.error(f"任务执行中发生异常: {e}", exc_info=False)

        # 6. 处理执行结果 (原逻辑中已包含，这里简化)
        logging.info(f"全部任务完成: {total_brands} 个品牌已处理。")

    except Exception as e:
        logging.error(f"脚本执行过程中发生未处理的异常: {e}", exc_info=True)
    finally:
        if progress_callback:
            progress_callback("finish")
        logging.info("脚本执行完毕。")


async def run_standalone():
    """独立运行时，创建完整的上下文并执行 main 函数"""
    from utils.logger import setup_logging_for_cli
    setup_logging_for_cli()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as async_client:
        # 1. 创建交互提供者
        interaction_provider = ConsoleInteractionProvider()

        # 2. 初始化核心管理器
        schema_manager = NotionSchemaManager(async_client, NOTION_TOKEN)
        bangumi_mapping_manager = BangumiMappingManager(interaction_provider)

        # 3. 初始化客户端
        notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
        bangumi_client = BangumiClient(
            async_client=async_client,
            schema_manager=schema_manager,
            mapping_manager=bangumi_mapping_manager,
            interaction_provider=interaction_provider,
        )

        # 4. 构建上下文
        context = {
            "notion": notion_client,
            "bangumi": bangumi_client,
            "schema_manager": schema_manager,
            "interaction_provider": interaction_provider,
            "async_client": async_client,
        }

        # 5. 执行主逻辑
        await main(context)


if __name__ == "__main__":
    asyncio.run(run_standalone())
