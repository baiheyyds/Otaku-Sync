# main.py
import asyncio
import sys

from core.brand_handler import handle_brand_info
from core.game_processor import process_and_sync_game
from core.init import close_context, init_context
from core.selector import select_game
from utils import logger
from utils.similarity_check import check_existing_similar_games


async def run_single_game_flow(context: dict):
    """处理单个游戏从搜索到入库的完整流程"""
    try:
        original_keyword = await asyncio.to_thread(
            input, "\n💡 请输入要搜索的游戏关键词 (或输入 'q' 退出): "
        )
        original_keyword = original_keyword.strip()
        if not original_keyword or original_keyword.lower() == "q":
            return False

        game, source = await select_game(
            context["dlsite"], context["getchu"], original_keyword, original_keyword
        )
        if not game or source == "cancel":
            logger.info("操作已取消。")
            return True

        logger.step(f"已选择来源: {source.upper()}, 游戏: {game['title']}")

        should_continue, updated_cache, mode, page_id = await check_existing_similar_games(
            context["notion"], game["title"], context["cached_titles"]
        )
        context["cached_titles"] = updated_cache
        if not should_continue:
            return True

        # --- 此处不再需要任何 driver 初始化逻辑 ---

        logger.info("正在并发获取 Dlsite, GGBases, Bangumi 的详细信息...")
        detail_task = context[source].get_game_detail(game["url"])
        ggbases_url_task = context["ggbases"].choose_or_parse_popular_url_with_requests(
            game["title"]
        )
        bangumi_id_task = context["bangumi"].search_and_select_bangumi_id(game["title"])

        detail, ggbases_url, bangumi_id = await asyncio.gather(
            detail_task, ggbases_url_task, bangumi_id_task
        )

        # 准备并发执行所有可能需要 Selenium 的任务
        selenium_tasks = []
        if ggbases_url:
            selenium_tasks.append(context["ggbases"].get_info_by_url_with_selenium(ggbases_url))

        brand_page_url = detail.get("品牌页链接")
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            selenium_tasks.append(
                context["dlsite"].get_brand_extra_info_with_selenium(brand_page_url)
            )
        elif source == "dlsite" and brand_page_url:
            logger.info(f"检测到商业品牌页({brand_page_url.split('/')[-2]})，跳过Selenium抓取。")

        # 并发执行所有非 Selenium 任务和已准备好的 Selenium 任务
        other_tasks = [
            context["bangumi"].fetch_game(bangumi_id) if bangumi_id else asyncio.sleep(0, result={})
        ]

        all_tasks = selenium_tasks + other_tasks
        results = await asyncio.gather(*all_tasks)

        # 解析结果
        ggbases_info = {}
        brand_extra_info = {}
        if ggbases_url:
            ggbases_info = results.pop(0)
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            brand_extra_info = results.pop(0)

        bangumi_info = results.pop(0)

        if brand_extra_info and detail.get("品牌页链接"):
            context["brand_extra_info_cache"][detail.get("品牌页链接")] = brand_extra_info
        logger.success("所有信息获取完毕！")

        getchu_brand_page_url = detail.get("品牌官网") if source == "getchu" else None
        brand_id = await handle_brand_info(
            source=source,
            dlsite_client=context["dlsite"],
            notion_client=context["notion"],
            brand_name=detail.get("品牌"),
            brand_page_url=detail.get("品牌页链接"),
            cache=context["brand_extra_info_cache"],
            bangumi_client=context["bangumi"],
            getchu_brand_page_url=getchu_brand_page_url,
        )

        created_page_id = await process_and_sync_game(
            game=game,
            detail=detail,
            size=ggbases_info.get("容量"),
            notion_client=context["notion"],
            brand_id=brand_id,
            ggbases_client=context["ggbases"],
            user_keyword=original_keyword,
            ggbases_detail_url=ggbases_url,
            ggbases_info=ggbases_info,
            bangumi_info=bangumi_info,
            source=source,
            selected_similar_page_id=page_id,
        )

        if created_page_id and bangumi_id:
            await context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)

        logger.success(f"游戏 '{game['title']}' 处理流程完成！\n")

    except Exception as e:
        logger.error(f"处理流程出现严重错误: {e}", exc_info=True)

    return True


async def main():
    """主函数"""
    context = await init_context()
    try:
        while True:
            should_continue = await run_single_game_flow(context)
            if not should_continue:
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warn("\n接收到中断信号，正在退出...")
    finally:
        logger.system("正在清理资源...")
        await close_context(context)
        context["brand_cache"].save_cache(context["brand_extra_info_cache"])
        logger.system("程序已安全退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被强制退出。")
