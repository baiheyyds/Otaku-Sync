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
    # ... 此函数不变 ...
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
        # --- 阶段 1: 用户输入与游戏选择 (不变) ---
        raw_input = await asyncio.to_thread(
            input, "\n💡 请输入游戏关键词 (追加 -m 进入手动模式，q 退出): "
        )
        raw_input = raw_input.strip()
        if not raw_input or raw_input.lower() == "q":
            return False
        manual_mode = raw_input.endswith(" -m")
        original_keyword = raw_input[:-3].strip() if manual_mode else raw_input
        if not original_keyword:
            logger.warn("请输入有效的游戏关键词。")
            return True
        game, source = await select_game(
            context["dlsite"], context["fanza"], original_keyword, original_keyword
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

        # --- 阶段 2: 并发获取所有“非交互式”的基础信息 ---
        logger.info(f"正在并发获取 {source.upper()} 详情和 GGBases 候选列表...")
        detail_task = context[source].get_game_detail(game["url"])
        ggbases_candidates_task = context["ggbases"].choose_or_parse_popular_url_with_requests(
            original_keyword
        )
        detail, ggbases_candidates = await asyncio.gather(detail_task, ggbases_candidates_task)

        # --- 阶段 3: 处理 GGBases 结果 (可能交互) ---
        ggbases_url = None
        if ggbases_candidates:
            if manual_mode:
                ggbases_url = await _select_ggbases_game_interactively(ggbases_candidates)
            else:
                best = max(ggbases_candidates, key=lambda x: x["popularity"])
                ggbases_url = best["url"]
                logger.success(f"[GGBases] 自动选择热度最高结果: {best['title']}")
        else:
            logger.warn("[GGBases] 未找到任何结果。")

        # --- 阶段 4: 串行获取可能需要交互的 Bangumi 信息 (核心修正) ---
        logger.info("正在获取 Bangumi 信息 (此过程可能需要您参与交互)...")
        # 4.1 获取 Bangumi ID (可能交互)
        bangumi_id = await context["bangumi"].search_and_select_bangumi_id(original_keyword)
        # 4.2 获取游戏详情 (可能因 infobox 触发交互)
        bangumi_game_info = await context["bangumi"].fetch_game(bangumi_id) if bangumi_id else {}
        # 4.3 获取品牌详情 (可能因 infobox 触发交互)
        brand_name = detail.get("品牌")
        bangumi_brand_info = (
            await context["bangumi"].fetch_brand_info_from_bangumi(brand_name) if brand_name else {}
        )

        # --- 阶段 5: 并发获取所有剩余的、无需交互的后台任务 ---
        logger.info("正在并发获取所有剩余的后台信息 (Selenium)...")
        selenium_tasks = []
        if ggbases_url:
            selenium_tasks.append(context["ggbases"].get_info_by_url_with_selenium(ggbases_url))
        brand_page_url = detail.get("品牌页链接")
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            selenium_tasks.append(
                context["dlsite"].get_brand_extra_info_with_selenium(brand_page_url)
            )

        ggbases_info, brand_extra_info = {}, {}
        if selenium_tasks:
            results = await asyncio.gather(*selenium_tasks, return_exceptions=True)
            idx = 0
            if ggbases_url:
                ggbases_info = results[idx] if not isinstance(results[idx], Exception) else {}
                idx += 1
            if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
                brand_extra_info = results[idx] if not isinstance(results[idx], Exception) else {}

        logger.success("所有信息获取完毕！")

        # --- 阶段 6: 数据处理与提交 (不变) ---
        if brand_extra_info and brand_page_url:
            context["brand_extra_info_cache"][brand_page_url] = brand_extra_info

        brand_id = None
        if brand_name:
            # handle_brand_info 现在是纯数据处理函数，不涉及网络I/O
            final_brand_info = await handle_brand_info(
                bangumi_brand_info=bangumi_brand_info,
                dlsite_extra_info=brand_extra_info,
            )
            brand_id = await context["notion"].create_or_update_brand(
                brand_name, **final_brand_info
            )

        created_page_id = await process_and_sync_game(
            game=game,
            detail=detail,
            notion_client=context["notion"],
            brand_id=brand_id,
            ggbases_client=context["ggbases"],
            user_keyword=original_keyword,
            ggbases_detail_url=ggbases_url,
            ggbases_info=ggbases_info,
            bangumi_info=bangumi_game_info,
            source=source,
            selected_similar_page_id=page_id,
        )
        if created_page_id and bangumi_id:
            await context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)
        logger.success(f"游戏 '{game['title']}' 处理流程完成！\n")

    except Exception as e:
        logger.error(f"处理流程出现严重错误: {e}")
        traceback_str = traceback.format_exc()
        if "Colors" in dir(logger):
            print(f"\n{logger.Colors.FAIL}{traceback_str}{logger.Colors.ENDC}")
        else:
            print(f"\n{traceback_str}")
    return True


async def main():
    # ... main 函数不变 ...
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
