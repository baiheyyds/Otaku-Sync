# main.py
import asyncio
import sys
import traceback

from core.brand_handler import check_brand_status, finalize_brand_update
from core.cache_warmer import warm_up_brand_cache_standalone
from core.game_processor import process_and_sync_game
from core.init import close_context, init_context
from core.selector import select_game
from utils import logger
from utils.similarity_check import check_existing_similar_games
from config.config_token import GAME_DB_ID


async def prompt_and_select_game(context: dict) -> tuple | None:
    """
    引导用户输入关键词，搜索并选择游戏。
    返回 (game, source, original_keyword, manual_mode) 或 None。
    """
    raw_input = await asyncio.to_thread(
        input, "\n💡 请输入游戏关键词 (追加 -m 进入手动模式，q 退出): "
    )
    raw_input = raw_input.strip()
    if not raw_input or raw_input.lower() == "q":
        return None  # Signal to exit the loop

    manual_mode = raw_input.endswith(" -m")
    original_keyword = raw_input[:-3].strip() if manual_mode else raw_input
    if not original_keyword:
        logger.warn("请输入有效的游戏关键词。")
        return "retry"  # Signal to retry the loop

    game, source = await select_game(
        context["dlsite"],
        context["fanza"],
        original_keyword,
        original_keyword,
        manual_mode=manual_mode,
    )

    if not game or source == "cancel":
        logger.info("操作已取消。")
        return "retry"

    logger.step(f"已选择来源: {source.upper()}, 游戏: {game['title']}")
    return game, source, original_keyword, manual_mode


async def check_and_prepare_sync(context: dict, game_title: str) -> tuple[bool, str | None]:
    """检查游戏是否已存在，并返回是否继续及可能存在的页面ID。"""
    should_continue, updated_cache, _, page_id = await check_existing_similar_games(
        context["notion"],
        game_title,
        context["cached_titles"],
    )
    context["cached_titles"] = updated_cache
    return should_continue, page_id


async def gather_primary_data(context: dict, keyword: str, game_url: str, source: str) -> dict:
    """并发获取第一批数据（Bangumi ID, 游戏详情, GGBases候选列表）。"""
    logger.info("正在并发获取所有来源的详细信息...")
    # 先执行非交互式任务
    background_tasks = {
        "detail": context[source].get_game_detail(game_url),
        "ggbases_candidates": context["ggbases"].choose_or_parse_popular_url_with_requests(keyword),
    }
    results = await asyncio.gather(*background_tasks.values(), return_exceptions=True)
    primary_data = {key: res for key, res in zip(background_tasks.keys(), results) if not isinstance(res, Exception)}

    # 再执行可能交互的任务
    try:
        primary_data['bangumi_id'] = await context["bangumi"].search_and_select_bangumi_id(keyword)
    except Exception as e:
        logger.error(f"获取 Bangumi ID 时出错: {e}")
        primary_data['bangumi_id'] = None
        
    return primary_data


async def _select_ggbases_game_interactively(candidates: list) -> dict | None:
    """交互式地从GGBases候选项中选择一个。"""
    print("\n🔍 GGBases 找到以下结果，请手动选择:")
    sorted_candidates = sorted(candidates, key=lambda x: x.get("popularity", 0), reverse=True)
    for idx, item in enumerate(sorted_candidates):
        size_info = f" (大小: {item.get('容量', '未知')})"
        print(f"  [{idx}] 🎮 {item['title']} (热度: {item.get('popularity', 0)}){size_info}")
    print("  [c] 取消选择")

    choice = await asyncio.to_thread(lambda: input("请输入序号选择 (默认0)，或输入'c'取消本次操作: ").strip().lower())
    if choice == "c":
        return None
    try:
        selected_idx = int(choice or 0)
        if 0 <= selected_idx < len(sorted_candidates):
            return sorted_candidates[selected_idx]
        logger.error("序号超出范围，请重试。")
    except (ValueError, IndexError):
        logger.error("无效输入，请输入数字或'c'。")
    return None


async def run_single_game_flow(context: dict) -> bool:
    """重构后的主流程，负责编排单个游戏的处理。"""
    try:
        # 步骤 1: 提示用户输入并选择游戏
        selection_result = await prompt_and_select_game(context)
        if selection_result is None:
            return False  # 用户选择退出
        if selection_result == "retry":
            return True  # 用户取消或无效输入，继续下一次循环
        game, source, keyword, manual_mode = selection_result

        # 步骤 2: 检查Notion中是否存在相似游戏
        should_continue, selected_similar_page_id = await check_and_prepare_sync(context, game["title"])
        if not should_continue:
            return True

        # 步骤 3: 并发获取第一批数据 (游戏详情, Bangumi, GGBases候选)
        primary_data = await gather_primary_data(context, keyword, game["url"], source)
        detail = primary_data.get("detail")
        if not detail:
            logger.error(f"获取游戏 '{game['title']}' 的核心详情失败，已跳过处理。")
            return True

        detail["source"] = source  # 注入来源信息
        bangumi_id = primary_data.get("bangumi_id")
        bangumi_game_info = {}
        if bangumi_id:
            bangumi_game_info = await context["bangumi"].fetch_game(bangumi_id)

        # ==================================================================
        # 步骤 4: 并发处理耗时的后台任务 (GGBases, Dlsite, Bangumi Brand)
        # ==================================================================
        secondary_tasks = {}

        # --- 准备 GGBases 任务 ---
        ggbases_candidates = primary_data.get("ggbases_candidates", [])
        selected_ggbases_game = None
        if ggbases_candidates:
            if manual_mode:
                selected_ggbases_game = await _select_ggbases_game_interactively(ggbases_candidates)
            else:
                selected_ggbases_game = max(ggbases_candidates, key=lambda x: x.get("popularity", 0))
            
            if selected_ggbases_game:
                logger.success(f"[GGBases] 已选择结果: {selected_ggbases_game['title']}")
                ggbases_url = selected_ggbases_game.get("url")
                if ggbases_url:
                    driver = await context["driver_factory"].get_driver("ggbases_driver")
                    if driver and not context["ggbases"].has_driver():
                        context["ggbases"].set_driver(driver)
                    secondary_tasks["ggbases_info"] = context["ggbases"].get_info_by_url_with_selenium(ggbases_url)

        # --- 准备品牌任务 ---
        raw_brand_name = detail.get("品牌")
        brand_name = context["brand_mapping_manager"].get_canonical_name(raw_brand_name)
        brand_page_id, needs_fetching = await check_brand_status(context, brand_name)
        if needs_fetching and brand_name:
            logger.step(f"品牌 '{brand_name}' 需要抓取新信息...")
            secondary_tasks["bangumi_brand_info"] = context["bangumi"].fetch_brand_info_from_bangumi(brand_name)
            
            dlsite_brand_url = detail.get("品牌页链接") if source == 'dlsite' else None
            if dlsite_brand_url and "/maniax/circle" in dlsite_brand_url:
                driver = await context["driver_factory"].get_driver("dlsite_driver")
                if driver and not context["dlsite"].has_driver():
                    context["dlsite"].set_driver(driver)
                secondary_tasks["brand_extra_info"] = context["dlsite"].get_brand_extra_info_with_selenium(dlsite_brand_url)

        # --- 执行所有后台任务 ---
        fetched_data = {}
        if secondary_tasks:
            logger.info(f"正在并发执行 {len(secondary_tasks)} 个后台任务 (Selenium/品牌信息)... ")
            results = await asyncio.gather(*secondary_tasks.values(), return_exceptions=True)
            fetched_data = {key: res for key, res in zip(secondary_tasks.keys(), results) if not isinstance(res, Exception)}
            logger.success("所有后台任务执行完毕！")

        # ==================================================================
        # 步骤 5: 收尾处理并同步到Notion
        # ==================================================================
        brand_id = await finalize_brand_update(context, brand_name, brand_page_id, fetched_data)
        ggbases_info = fetched_data.get("ggbases_info", {})

        # 步骤 6: 整合所有信息并同步到Notion
        created_page_id = await process_and_sync_game(
            game=game,
            detail=detail,
            notion_client=context["notion"],
            brand_id=brand_id,
            ggbases_client=context["ggbases"],
            user_keyword=keyword,
            notion_game_schema=context["schema_manager"].get_schema(GAME_DB_ID),
            tag_manager=context["tag_manager"],
            name_splitter=context["name_splitter"],
            interaction_provider=context["interaction_provider"],
            ggbases_detail_url=(selected_ggbases_game or {}).get("url"),
            ggbases_info=ggbases_info or {},
            ggbases_search_result=selected_ggbases_game or {},
            bangumi_info=bangumi_game_info,
            source=source,
            selected_similar_page_id=selected_similar_page_id,
        )

        # 步骤 6.1: 如果是创建了新页面（而不是更新），则更新本地缓存以实现实时查重
        if created_page_id and not selected_similar_page_id:
            new_game_entry = {"id": created_page_id, "title": game["title"]}
            context["cached_titles"].append(new_game_entry)
            logger.cache(f"实时查重缓存已更新: {game['title']}")

        # 步骤 7: 如果成功创建页面且有Bangumi ID，则关联角色
        if created_page_id and bangumi_id:
            await context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)

        logger.success(f"游戏 '{game['title']}' 处理流程完成！\n")

    except Exception as e:
        logger.error(f"处理流程出现严重错误: {e}")
        traceback_str = traceback.format_exc()
        # 保持原有打印方式
        if "Colors" in dir(logger):
            print(f"\n{logger.Colors.FAIL}{traceback_str}{logger.Colors.ENDC}")
        else:
            print(f"\n{traceback_str}")

    return True  # 表示可以继续下一次循环


async def main():
    """程序主入口。"""
    context = await init_context()
    logger.system("[诊断] 准备创建品牌缓存预热后台任务...")
    asyncio.create_task(warm_up_brand_cache_standalone()) # 在后台预热品牌缓存
    logger.system("[诊断] 品牌缓存预热后台任务已创建。")
    try:
        while True:
            if not await run_single_game_flow(context):
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warn("\n接收到中断信号，正在退出...")
    finally:
        logger.system("正在清理资源...")
        await close_context(context)
        logger.system("程序已安全退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被强制退出。")