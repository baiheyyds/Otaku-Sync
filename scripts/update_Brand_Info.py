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


async def main():
    """主执行函数"""
    logger.system("启动品牌信息批量更新脚本...")

    # 1. 初始化所有核心组件，与 main.py 保持一致
    async_client = httpx.AsyncClient(timeout=20, follow_redirects=True, http2=True)

    interaction_provider = ConsoleInteractionProvider()
    bgm_mapper = BangumiMappingManager(interaction_provider)
    notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, async_client)
    schema_manager = NotionSchemaManager(notion_client)

    # 在开始前，先加载好数据库的 Schema
    await schema_manager.initialize_schema(BRAND_DB_ID, "厂商数据库")
    await schema_manager.initialize_schema(CHARACTER_DB_ID, "角色数据库")

    bangumi_client = BangumiClient(notion_client, bgm_mapper, schema_manager, async_client)

    try:
        # 2. 从 Notion 获取所有品牌页面
        logger.info("正在从 Notion 获取所有品牌页面...")
        all_brand_pages = await notion_client.get_all_pages_from_db(BRAND_DB_ID)
        if not all_brand_pages:
            logger.error("未能从 Notion 获取到任何品牌信息，脚本终止。")
            return

        total_brands = len(all_brand_pages)
        logger.success(f"成功获取到 {total_brands} 个品牌，开始逐一更新。")

        # 3. 遍历每个品牌并更新
        for i, brand_page in enumerate(all_brand_pages, 1):
            # 从页面属性中提取品牌名
            brand_name = notion_client.get_page_title(brand_page)
            if not brand_name:
                logger.warn(
                    f"[{i}/{total_brands}] 跳过一个没有名称的品牌页面 (Page ID: {brand_page.get('id')})"
                )
                continue

            logger.step(f"[{i}/{total_brands}] 正在处理品牌: {brand_name}")

            # 4. 复用 BangumiClient 的核心方法来获取信息
            # 这一步包含了搜索、相似度匹配、infobox 动态解析等所有复杂逻辑
            bangumi_info = await bangumi_client.fetch_brand_info_from_bangumi(brand_name)

            if not bangumi_info:
                logger.warn(f"在 Bangumi 上未能找到 '{brand_name}' 的匹配信息，跳过更新。")
                await asyncio.sleep(1.2)  # 即使失败也稍作等待，避免对 API 造成冲击
                continue

            # 5. 复用 NotionClient 的核心方法来更新页面
            # 这一步包含了构建 payload 和发送请求的所有逻辑
            # 注意：我们将 page_id 传入，使其强制执行“更新”操作
            success = await notion_client.create_or_update_brand(
                brand_name=brand_name, page_id=brand_page.get("id"), **bangumi_info
            )

            if success:
                logger.success(f"品牌 '{brand_name}' 的信息已成功更新。")
            else:
                logger.error(f"品牌 '{brand_name}' 的信息更新失败。")

            # 尊重 Bangumi API 的速率限制
            await asyncio.sleep(1.2)

    except Exception as e:
        logger.error(f"脚本执行过程中发生未处理的异常: {e}", exc_info=True)
    finally:
        # 6. 优雅地关闭资源
        await async_client.aclose()
        logger.system("HTTP 客户端已关闭，脚本执行完毕。")


if __name__ == "__main__":
    # We might need to adjust this part if methods are no longer monkey-patched
    # For now, assuming the client has the necessary methods.
    asyncio.run(main())
