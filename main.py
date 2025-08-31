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
from config.config_token import GAME_DB_ID
from utils.driver import create_driver


# --- 【核心修复】让此函数返回完整的选择结果字典，而不仅仅是URL ---
async def _select_ggbases_game_interactively(candidates: list) -> dict | None:
    print("\n🔍 GGBases 找到以下结果，请手动选择:")
    sorted_candidates = sorted(candidates, key=lambda x: x["popularity"], reverse=True)
    for idx, item in enumerate(sorted_candidates):
        # 同时显示大小信息
        size_info = f" (大小: {item.get('容量', '未知')})"
        print(f"  [{idx}] 🎮 {item['title']} (热度: {item['popularity']}){size_info}")
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
                return sorted_candidates[selected_idx]  # 返回整个字典
            else:
                logger.error("序号超出范围，请重试。")
        except (ValueError, IndexError):
            logger.error("无效输入，请输入数字或'c'。")


async def get_or_create_driver(context: dict, driver_key: str):
    # ... 此函数无变化 ...
    if context[driver_key] is None:
        logger.system(f"正在按需创建 {driver_key}...")
        driver = await asyncio.to_thread(create_driver)
        context[driver_key] = driver
        if driver_key == "dlsite_driver":
            context["dlsite"].set_driver(driver)
        elif driver_key == "ggbases_driver":
            context["ggbases"].set_driver(driver)
        logger.success(f"{driver_key} 已成功创建并设置。")
    return context[driver_key]


async def run_single_game_flow(context: dict):
    try:
        # ... 流程 1, 2, 3, 4 无变化 ...
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
            context["dlsite"],
            context["fanza"],
            original_keyword,
            original_keyword,
            manual_mode=manual_mode,
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

        logger.info("正在获取 Bangumi 信息 (此过程可能需要您参与交互)...")
        bangumi_id = await context["bangumi"].search_and_select_bangumi_id(original_keyword)

        logger.info("正在并发获取所有来源的详细信息...")
        tasks = {}
        tasks["detail"] = context[source].get_game_detail(game["url"])
        tasks["ggbases_candidates"] = context["ggbases"].choose_or_parse_popular_url_with_requests(
            original_keyword
        )
        if bangumi_id:
            tasks["bangumi_game_info"] = context["bangumi"].fetch_game(bangumi_id)

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        task_results = {
            key: res for key, res in zip(tasks.keys(), results) if not isinstance(res, Exception)
        }
        detail = task_results.get("detail", {})
        ggbases_candidates = task_results.get("ggbases_candidates", [])
        bangumi_game_info = task_results.get("bangumi_game_info", {})

        # --- 【核心修复】处理GGBases选择，并保留完整结果 ---
        selected_ggbases_game = None  # 初始化为 None
        if ggbases_candidates:
            if manual_mode:
                selected_ggbases_game = await _select_ggbases_game_interactively(ggbases_candidates)
            else:
                selected_ggbases_game = max(ggbases_candidates, key=lambda x: x["popularity"])
                logger.success(f"[GGBases] 自动选择热度最高结果: {selected_ggbases_game['title']}")

        # 从选择结果中获取 URL
        ggbases_url = selected_ggbases_game.get("url") if selected_ggbases_game else None
        # --- [修复结束] ---

        # ... 流程 5.2, 5.3 无变化 ...
        selenium_tasks = {}
        if ggbases_url:
            await get_or_create_driver(context, "ggbases_driver")
            selenium_tasks["ggbases_info"] = context["ggbases"].get_info_by_url_with_selenium(
                ggbases_url
            )
        brand_name = detail.get("品牌")
        brand_page_url = detail.get("品牌页链接")
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            await get_or_create_driver(context, "dlsite_driver")
            selenium_tasks["brand_extra_info"] = context[
                "dlsite"
            ].get_brand_extra_info_with_selenium(brand_page_url)
        if brand_name:
            selenium_tasks["bangumi_brand_info"] = context["bangumi"].fetch_brand_info_from_bangumi(
                brand_name
            )
        if selenium_tasks:
            logger.info("正在并发获取剩余的后台信息 (Selenium & Bangumi Brand)...")
            selenium_results_list = await asyncio.gather(
                *selenium_tasks.values(), return_exceptions=True
            )
            selenium_results = {
                key: res
                for key, res in zip(selenium_tasks.keys(), selenium_results_list)
                if not isinstance(res, Exception)
            }
            ggbases_info = selenium_results.get("ggbases_info", {})
            brand_extra_info = selenium_results.get("brand_extra_info", {})
            bangumi_brand_info = selenium_results.get("bangumi_brand_info", {})
        else:
            ggbases_info, brand_extra_info, bangumi_brand_info = {}, {}, {}
        logger.success("所有信息获取完毕！")

        # --- 流程 6 无变化 ...
        if brand_extra_info and brand_page_url:
            context["brand_extra_info_cache"][brand_page_url] = brand_extra_info
        brand_id = None
        if brand_name:
            final_brand_info = await handle_brand_info(
                bangumi_brand_info=bangumi_brand_info,
                dlsite_extra_info=brand_extra_info,
            )
            brand_id = await context["notion"].create_or_update_brand(
                brand_name, **final_brand_info
            )

        # --- 【核心修复】将完整的 ggbases 选择结果传递下去 ---
        created_page_id = await process_and_sync_game(
            game=game,
            detail=detail,
            notion_client=context["notion"],
            brand_id=brand_id,
            ggbases_client=context["ggbases"],
            user_keyword=original_keyword,
            notion_game_schema=context["schema_manager"]._schemas[GAME_DB_ID],
            tag_manager=context["tag_manager"],
            ggbases_detail_url=ggbases_url,
            ggbases_info=ggbases_info,
            ggbases_search_result=selected_ggbases_game,  # 传递完整结果
            bangumi_info=bangumi_game_info,
            source=source,
            selected_similar_page_id=page_id,
        )
        # --- [修复结束] ---

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
