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


async def get_or_create_driver(context: dict, driver_key: str):
    if context[driver_key] is None:
        logger.system(f"正在按需创建 {driver_key}...")
        driver = await asyncio.to_thread(create_driver)
        context[driver_key] = driver
        # 别忘了将 driver 设置到对应的 client 中
        if driver_key == "dlsite_driver":
            context["dlsite"].set_driver(driver)
        elif driver_key == "ggbases_driver":
            context["ggbases"].set_driver(driver)
        logger.success(f"{driver_key} 已成功创建并设置。")
    return context[driver_key]


async def run_single_game_flow(context: dict):
    try:
        # --- 阶段 1: 用户输入与游戏选择 (无变化) ---
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
            manual_mode=manual_mode,  # <-- 添加这一行
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

        # --- 阶段 2: 交互式获取 Bangumi ID (这是流程中的第一个潜在阻塞点) ---
        logger.info("正在获取 Bangumi 信息 (此过程可能需要您参与交互)...")
        bangumi_id = await context["bangumi"].search_and_select_bangumi_id(original_keyword)

        # --- 阶段 3: 创建一个并发任务池 ---
        logger.info("正在并发获取所有来源的详细信息...")
        tasks = {}

        # 3.1 添加主要来源 (DLsite/Fanza) 的详情任务
        tasks["detail"] = context[source].get_game_detail(game["url"])

        # 3.2 添加 GGBases 的搜索任务
        tasks["ggbases_candidates"] = context["ggbases"].choose_or_parse_popular_url_with_requests(
            original_keyword
        )

        # 3.3 如果有 Bangumi ID，添加 Bangumi 游戏详情任务 (可能触发交互)
        if bangumi_id:
            tasks["bangumi_game_info"] = context["bangumi"].fetch_game(bangumi_id)

        # --- 阶段 4: 执行第一轮并发，获取后续任务所需的前置信息 ---
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # 将结果从列表解包回字典
        task_results = {
            key: res for key, res in zip(tasks.keys(), results) if not isinstance(res, Exception)
        }

        detail = task_results.get("detail", {})
        ggbases_candidates = task_results.get("ggbases_candidates", [])
        bangumi_game_info = task_results.get("bangumi_game_info", {})

        # --- 阶段 5: 处理需要前置信息的后续并发任务 ---

        # 5.1 处理 GGBases (可能交互)
        ggbases_url = None
        if ggbases_candidates:
            if manual_mode:
                ggbases_url = await _select_ggbases_game_interactively(ggbases_candidates)
            else:
                best = max(ggbases_candidates, key=lambda x: x["popularity"])
                ggbases_url = best["url"]
                logger.success(f"[GGBases] 自动选择热度最高结果: {best['title']}")

        # 5.2 准备第二轮并发任务 (Selenium 和 Bangumi 品牌)
        selenium_tasks = {}
        if ggbases_url:
            # 【修改】调用前确保 driver 存在
            await get_or_create_driver(context, "ggbases_driver")
            selenium_tasks["ggbases_info"] = context["ggbases"].get_info_by_url_with_selenium(
                ggbases_url
            )

        brand_name = detail.get("品牌")
        brand_page_url = detail.get("品牌页链接")

        # 只有 DLsite 的品牌页链接才用于 Selenium
        if source == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
            # 【修改】调用前确保 driver 存在
            await get_or_create_driver(context, "dlsite_driver")
            selenium_tasks["brand_extra_info"] = context[
                "dlsite"
            ].get_brand_extra_info_with_selenium(brand_page_url)

        # Bangumi 品牌信息获取 (可能触发交互)
        if brand_name:
            selenium_tasks["bangumi_brand_info"] = context["bangumi"].fetch_brand_info_from_bangumi(
                brand_name
            )

        # 5.3 执行第二轮并发
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

        # --- 阶段 6: 数据处理与提交 (与原逻辑基本一致) ---
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

        created_page_id = await process_and_sync_game(
            game=game,
            detail=detail,
            notion_client=context["notion"],
            brand_id=brand_id,
            ggbases_client=context["ggbases"],
            user_keyword=original_keyword,
            # 2. 从 context 中取出 schema_manager，并用 GAME_DB_ID 获取游戏数据库的结构
            notion_game_schema=context["schema_manager"]._schemas[GAME_DB_ID],
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
