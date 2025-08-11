# main.py
import asyncio
import sys
import traceback

from core.brand_handler import handle_brand_info
from core.game_processor import process_and_sync_game
from core.init import close_context, init_context
from core.selector import select_game
from utils import logger
from utils.similarity_check import check_existing_similar_games


async def _select_ggbases_game_interactively(candidates: list) -> str | None:
    print("\n🔍 GGBases 找到以下结果，请手动选择:")
    sorted_candidates = sorted(candidates, key=lambda x: x["popularity"], reverse=True)
    for idx, item in enumerate(sorted_candidates):
        print(f"  [{idx}] 🎮 {item['title']} (热度: {item['popularity']})")

    print("  [c] 取消选择")

    def _get_input():
        prompt = "请输入序号选择 (默认0)，或输入'c'取消本次操作: "
        return input(prompt).strip().lower()

    while True:
        choice = await asyncio.to_thread(_get_input)
        if choice == "c":
            return None
        try:
            selected_idx = int(choice or 0)
            if 0 <= selected_idx < len(sorted_candidates):
                return sorted_candidates[selected_idx]["url"]
            else:
                logger.error("序号超出范围，请重试。")
        except (ValueError, IndexError):
            logger.error("无效输入，请输入数字或'c'。")


async def run_single_game_flow(context: dict):
    try:
        raw_input = await asyncio.to_thread(
            input, "\n💡 请输入游戏关键词 (追加 -m 进入手动模式，q 退出): "
        )
        raw_input = raw_input.strip()

        if not raw_input or raw_input.lower() == "q":
            return False

        manual_mode = False
        if raw_input.endswith(" -m"):
            manual_mode = True
            original_keyword = raw_input[:-3].strip()
            logger.system(f"已为 '{original_keyword}' 启动单次手动模式。")
        else:
            original_keyword = raw_input

        if not original_keyword:
            logger.warn("请输入有效的游戏关键词。")
            return True

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

        # --- 核心改动：使用用户输入的 original_keyword 进行 GGBases 搜索 ---
        ggbases_candidates = await context["ggbases"].choose_or_parse_popular_url_with_requests(
            original_keyword
        )
        # --- 核心改动结束 ---

        ggbases_url = None
        if ggbases_candidates:
            if manual_mode:
                ggbases_url = await _select_ggbases_game_interactively(ggbases_candidates)
                if not ggbases_url:
                    logger.info("已取消GGBases选择。")
            else:
                best = max(ggbases_candidates, key=lambda x: x["popularity"])
                ggbases_url = best["url"]
                logger.success(f"[GGBases] 自动选择热度最高结果: {best['title']}")
        else:
            logger.warn("[GGBases] 未找到任何结果。")

        logger.info("正在并发获取 Dlsite, GGBases, Bangumi 的详细信息...")
        detail_task = context[source].get_game_detail(game["url"])
        bangumi_id_task = context["bangumi"].search_and_select_bangumi_id(game["title"])

        detail, bangumi_id = await asyncio.gather(detail_task, bangumi_id_task)

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

        other_tasks = [
            context["bangumi"].fetch_game(bangumi_id) if bangumi_id else asyncio.sleep(0, result={})
        ]

        all_tasks = selenium_tasks + other_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        ggbases_info, brand_extra_info, bangumi_info = {}, {}, {}
        result_idx = 0
        if ggbases_url:
            ggbases_info = (
                results[result_idx] if not isinstance(results[result_idx], Exception) else {}
            )
            result_idx += 1
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            brand_extra_info = (
                results[result_idx] if not isinstance(results[result_idx], Exception) else {}
            )
            result_idx += 1
        bangumi_info = results[result_idx] if not isinstance(results[result_idx], Exception) else {}

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
        logger.error(f"处理流程出现严重错误: {e}")
        traceback_str = traceback.format_exc()
        print(f"\n{Colors.FAIL}{traceback_str}{Colors.ENDC}")
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
    from utils.logger import Colors

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被强制退出。")
