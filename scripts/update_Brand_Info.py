# scripts/update_all_brands.py
# 该脚本用于批量更新 Notion 中所有品牌的 Bangumi 信息
import asyncio
import os
import sys

import httpx

# 将项目根目录添加到 Python 路径中，以便能够导入其他模块
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from clients.bangumi_client import BangumiClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.interaction import ConsoleInteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager
from utils import logger


from asyncio import Semaphore
from tqdm.asyncio import tqdm_asyncio

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
        logger.warn(f"跳过一个没有名称的品牌页面 (Page ID: {page_id})")
        return

    # 使用信号量来限制对 Bangumi API 的并发访问
    async with bgm_semaphore:
        # 每次请求前都短暂 sleep，模拟更真实的用户行为，进一步降低被拒绝的风险
        await asyncio.sleep(1.2)
        bangumi_info = await bangumi_client.fetch_brand_info_from_bangumi(brand_name)

    if not bangumi_info:
        logger.warn(f"在 Bangumi 上未能找到 '{brand_name}' 的匹配信息，跳过更新。")
        return

    success = await notion_client.create_or_update_brand(
        brand_name=brand_name, page_id=page_id, **bangumi_info
    )

    if success:
        logger.success(f"品牌 '{brand_name}' 的信息已成功更新。")
    else:
        logger.error(f"品牌 '{brand_name}' 的信息更新失败。")


async def main():
    """主执行函数"""
    logger.system("启动品牌信息批量更新脚本...")

    # 1. 初始化所有核心组件
    async_client = httpx.AsyncClient(timeout=20, follow_redirects=True, http2=True)
    interaction_provider = ConsoleInteractionProvider()
    bgm_mapper = BangumiMappingManager(interaction_provider)
    notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
    schema_manager = NotionSchemaManager(notion_client)
    bangumi_client = BangumiClient(notion_client, bgm_mapper, schema_manager, async_client)

    # Bangumi API 速率限制信号量，允许1个并发
    bgm_semaphore = Semaphore(1)

    try:
        # 2. 预加载 Schema
        await schema_manager.initialize_schema(BRAND_DB_ID, "厂商数据库")
        await schema_manager.initialize_schema(CHARACTER_DB_ID, "角色数据库")

        # 3. 从 Notion 获取所有品牌页面
        logger.info("正在从 Notion 获取所有品牌页面...")
        all_brand_pages = await notion_client.get_all_pages_from_db(BRAND_DB_ID)
        if not all_brand_pages:
            logger.error("未能从 Notion 获取到任何品牌信息，脚本终止。")
            return

        total_brands = len(all_brand_pages)
        logger.success(f"成功获取到 {total_brands} 个品牌，开始并发更新...")

        # 4. 创建所有并发任务
        tasks = [
            process_brand_page(
                page, notion_client, bangumi_client, bgm_semaphore
            )
            for page in all_brand_pages
        ]

        # 5. 使用 tqdm_asyncio.gather 执行任务并显示进度条
        results = await tqdm_asyncio.gather(
            *tasks, desc="更新品牌信息", return_exceptions=True
        )

        # 6. 处理执行结果
        success_count = 0
        error_count = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务执行中发生异常: {result}", exc_info=False)
                error_count += 1
            else:
                success_count += 1
        
        logger.system(f"全部任务完成: {success_count} 个成功, {error_count} 个失败。")

    except Exception as e:
        logger.error(f"脚本执行过程中发生未处理的异常: {e}", exc_info=True)
    finally:
        # 7. 优雅地关闭资源
        await async_client.aclose()
        logger.system("HTTP 客户端已关闭，脚本执行完毕。")


if __name__ == "__main__":
    # We might need to adjust this part if methods are no longer monkey-patched
    # For now, assuming the client has the necessary methods.
    asyncio.run(main())
