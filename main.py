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
        logger.info("操作已取消。 সন")
        return "retry"

    logger.step(f"已选择来源: {source.upper()}, 游戏: {game['title']}")
    return game, source, original_keyword, manual_mode


async def check_and_prepare_sync(context: dict, game_title: str) -> tuple[bool, str | None]:
    """检查游戏是否已存在，并返回是否继续及可能存在的页面ID。"""
    should_continue, updated_cache, _, page_id = await check_existing_similar_games(
        context["notion"], game_title, context["cached_titles"]
    )
    context["cached_titles"] = updated_cache
    return should_continue, page_id


async def gather_primary_data(context: dict, keyword: str, game_url: str, source: str) -> dict:
    """并发获取第一批数据（Bangumi ID, 游戏详情, GGBases候选列表）。"""
    logger.info("正在并发获取所有来源的详细信息...")
    tasks = {
        "detail": context[source].get_game_detail(game_url),
        "ggbases_candidates": context["ggbases"].choose_or_parse_popular_url_with_requests(keyword),
        "bangumi_id": context["bangumi"].search_and_select_bangumi_id(keyword),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    return {key: res for key, res in zip(tasks.keys(), results) if not isinstance(res, Exception)}


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
        logger.error("序号超出范围，请重试。 সন")
    except (ValueError, IndexError):
        logger.error("无效输入，请输入数字或'c'。 সন")
    return None


async def gather_secondary_data(context: dict, primary_data: dict, detail: dict, manual_mode: bool) -> dict:
    """根据第一批数据，获取需要Selenium或有依赖关系的第二批数据。"""
    ggbases_candidates = primary_data.get("ggbases_candidates", [])
    selected_ggbases_game = None
    if ggbases_candidates:
        if manual_mode:
            selected_ggbases_game = await _select_ggbases_game_interactively(ggbases_candidates)
        else:
            selected_ggbases_game = max(ggbases_candidates, key=lambda x: x.get("popularity", 0))
            logger.success(f"[GGBases] 自动选择热度最高结果: {selected_ggbases_game['title']}")

    ggbases_url = selected_ggbases_game.get("url") if selected_ggbases_game else None

    selenium_tasks = {}
    if ggbases_url:
        await get_or_create_driver(context, "ggbases_driver")
        selenium_tasks["ggbases_info"] = context["ggbases"].get_info_by_url_with_selenium(ggbases_url)

    brand_name = detail.get("品牌")
    brand_page_url = detail.get("品牌页链接")
    if detail.get("source") == "dlsite" and brand_page_url and "/maniax/circle" in brand_page_url:
        await get_or_create_driver(context, "dlsite_driver")
        selenium_tasks["brand_extra_info"] = context["dlsite"].get_brand_extra_info_with_selenium(brand_page_url)

    if brand_name:
        selenium_tasks["bangumi_brand_info"] = context["bangumi"].fetch_brand_info_from_bangumi(brand_name)

    if not selenium_tasks:
        return {"selected_ggbases_game": selected_ggbases_game}

    logger.info("正在并发获取剩余的后台信息 (Selenium & Bangumi Brand)...")
    results = await asyncio.gather(*selenium_tasks.values(), return_exceptions=True)
    output = {key: res for key, res in zip(selenium_tasks.keys(), results) if not isinstance(res, Exception)}
    output["selected_ggbases_game"] = selected_ggbases_game
    return output


async def process_and_update_brand(context: dict, detail: dict, secondary_data: dict) -> str | None:
    """处理并创建/更新品牌信息。"""
    brand_name = detail.get("品牌")
    if not brand_name:
        return None

    final_brand_info = await handle_brand_info(
        bangumi_brand_info=secondary_data.get("bangumi_brand_info", {}),
        dlsite_extra_info=secondary_data.get("brand_extra_info", {}),
    )
    brand_id = await context["notion"].create_or_update_brand(brand_name, **final_brand_info)
    return brand_id


async def get_or_create_driver(context: dict, driver_key: str):
    """向 DriverFactory 请求一个驱动程序，如果需要则等待其创建完成。"""
    driver_factory = context["driver_factory"]
    driver = await driver_factory.get_driver(driver_key)

    if not driver:
        logger.error(f"无法获取 {driver_key}，后续相关操作将跳过。 সন")
        return None

    # 确保客户端与驱动程序关联
    if driver_key == "dlsite_driver":
        # 检查客户端是否已经设置了驱动，避免重复设置
        if not context["dlsite"].has_driver():
            context["dlsite"].set_driver(driver)
            logger.info(f"{driver_key} 已设置到 DlsiteClient。 সন")
    elif driver_key == "ggbases_driver":
        if not context["ggbases"].has_driver():
            context["ggbases"].set_driver(driver)
            logger.info(f"{driver_key} 已设置到 GGBasesClient。 সন")
            
    return driver


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

        # 步骤 3: 并发获取第一批数据
        primary_data = await gather_primary_data(context, keyword, game["url"], source)
        detail = primary_data.get("detail", {})
        detail["source"] = source  # 注入来源信息
        bangumi_id = primary_data.get("bangumi_id")
        bangumi_game_info = {}
        if bangumi_id:
            bangumi_game_info = await context["bangumi"].fetch_game(bangumi_id)

        # 步骤 4: 根据第一批数据，获取第二批（需要Selenium或有依赖的）数据
        secondary_data = await gather_secondary_data(context, primary_data, detail, manual_mode)
        logger.success("所有信息获取完毕！ সন")

        # 步骤 5: 处理并更新品牌信息
        brand_id = await process_and_update_brand(context, detail, secondary_data)

        # 步骤 6: 整合所有信息并同步到Notion
        selected_ggbases_game = secondary_data.get("selected_ggbases_game") or {}
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
            ggbases_detail_url=selected_ggbases_game.get("url"),
            ggbases_info=secondary_data.get("ggbases_info", {}),
            ggbases_search_result=selected_ggbases_game,
            bangumi_info=bangumi_game_info,
            source=source,
            selected_similar_page_id=selected_similar_page_id,
        )

        # --- [修复 1] --- #
        # 步骤 6.1: 如果是创建了新页面（而不是更新），则更新本地缓存以实现实时查重
        if created_page_id and not selected_similar_page_id:
            new_game_entry = {"id": created_page_id, "title": game["title"]}
            context["cached_titles"].append(new_game_entry)
            logger.cache(f"实时查重缓存已更新: {game['title']}")
        # --- [修复结束] --- #

        # 步骤 7: 如果成功创建页面且有Bangumi ID，则关联角色
        if created_page_id and bangumi_id:
            await context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)

        logger.success(f"游戏 '{game['title']}' 处理流程完成！\n সন")

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
    try:
        while True:
            if not await run_single_game_flow(context):
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warn("\n接收到中断信号，正在退出...")
    finally:
        logger.system("正在清理资源...")
        await close_context(context)
        # 这个保存操作在 close_context 中已经有了，但为了保险起见可以保留
        if context.get("brand_cache") and context.get("brand_extra_info_cache"):
            context["brand_cache"].save_cache(context["brand_extra_info_cache"])
        logger.system("程序已安全退出。 সন")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被强制退出。 সন")
