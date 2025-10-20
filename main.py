# main.py
import asyncio
import logging

from config.config_token import GAME_DB_ID
from core.brand_handler import check_brand_status, finalize_brand_update
from core.cache_warmer import warm_up_brand_cache_standalone
from core.game_processor import process_and_sync_game
from core.init import close_context, init_context
from core.selector import select_game
from utils.logger import setup_logging_for_cli
from utils.similarity_check import check_existing_similar_games


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
        logging.warning("⚠️ 请输入有效的游戏关键词。")
        return "retry"  # Signal to retry the loop

    game, source = await select_game(
        context["dlsite"],
        context["fanza"],
        original_keyword,
        original_keyword,
        manual_mode=manual_mode,
    )

    if not game or source == "cancel":
        logging.info("操作已取消。")
        return "retry"

    logging.info(f"🚀 已选择来源: {source.upper()}, 游戏: {game['title']}")
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


async def _fetch_ggbases_data_cli(context: dict, keyword: str, manual_mode: bool) -> dict:
    """ (CLI)获取GGBases数据，包含独立的错误处理和交互逻辑。"""
    logging.info("🔍 [GGBases] 开始获取 GGBases 数据...")
    try:
        candidates = await context["ggbases"].choose_or_parse_popular_url_with_requests(keyword)
        if not candidates:
            logging.warning("⚠️ [GGBases] 未找到任何候选。")
            return {}

        selected_game = None
        if manual_mode:
            logging.info("🔍 [GGBases] 手动模式，需要用户选择。")
            print("\n🔍 GGBases 找到以下结果，请手动选择:")
            sorted_candidates = sorted(candidates, key=lambda x: x.get("popularity", 0), reverse=True)
            for idx, item in enumerate(sorted_candidates):
                size_info = f" (大小: {item.get('容量', '未知')})"
                print(f"  [{idx}] 🎮 {item['title']} (热度: {item.get('popularity', 0)}){size_info}")
            print("  [c] 取消选择")
            choice = await asyncio.to_thread(lambda: input("请输入序号选择 (默认0)，或输入'c'取消本次操作: ").strip().lower())
            if choice == "c":
                selected_game = None
            else:
                selected_idx = int(choice or 0)
                if 0 <= selected_idx < len(sorted_candidates):
                    selected_game = sorted_candidates[selected_idx]
        else:
            selected_game = max(candidates, key=lambda x: x.get("popularity", 0))

        if not selected_game:
            logging.info("🔍 [GGBases] 用户未选择或无有效结果。")
            return {}

        logging.info(f"✅ [GGBases] 已选择结果: {selected_game['title']}")
        url = selected_game.get("url")
        if not url:
            return {"selected_game": selected_game}

        driver = await context["driver_factory"].get_driver("ggbases_driver")
        if driver and not context["ggbases"].has_driver():
            context["ggbases"].set_driver(driver)

        info = await context["ggbases"].get_info_by_url_with_selenium(url)
        logging.info("✅ [GGBases] Selenium 抓取完成。")
        return {"info": info, "selected_game": selected_game}
    except Exception as e:
        logging.error(f"❌ [GGBases] 获取数据时出错: {e}")
        return {}


async def _fetch_bangumi_data_cli(context: dict, keyword: str) -> dict:
    """ (CLI)获取Bangumi数据，包含独立的错误处理。"""
    logging.info("🔍 [Bangumi] 开始获取 Bangumi 数据...")
    try:
        bangumi_id = await context["bangumi"].search_and_select_bangumi_id(keyword)
        if not bangumi_id:
            logging.warning("⚠️ [Bangumi] 未找到或未选择 Bangumi 条目。")
            return {}

        logging.info(f"🔍 [Bangumi] 已确认 Bangumi ID: {bangumi_id}, 正在获取详细信息...")
        game_info = await context["bangumi"].fetch_game(bangumi_id)
        logging.info("✅ [Bangumi] 游戏详情获取完成。")
        return {"game_info": game_info, "bangumi_id": bangumi_id}
    except Exception as e:
        logging.error(f"❌ [Bangumi] 获取数据时出错: {e}")
        return {}


async def _fetch_and_process_brand_data_cli(context: dict, detail: dict, source: str) -> dict:
    """ (CLI)处理品牌信息，包含独立的错误处理和数据抓取。"""
    logging.info("🔍 [品牌] 开始处理品牌信息...")
    try:
        raw_brand_name = detail.get("品牌")
        brand_name = context["brand_mapping_manager"].get_canonical_name(raw_brand_name)
        brand_page_id, needs_fetching = await check_brand_status(context, brand_name)

        fetched_data = {}
        if needs_fetching and brand_name:
            logging.info(f"🚀 品牌 '{brand_name}' 需要抓取新信息...")
            tasks = {}
            tasks["bangumi_brand_info"] = context["bangumi"].fetch_brand_info_from_bangumi(brand_name)

            dlsite_brand_url = detail.get("品牌页链接") if source == 'dlsite' else None
            if dlsite_brand_url and "/maniax/circle" in dlsite_brand_url:
                driver = await context["driver_factory"].get_driver("dlsite_driver")
                if driver and not context["dlsite"].has_driver():
                    context["dlsite"].set_driver(driver)
                tasks["brand_extra_info"] = context["dlsite"].get_brand_extra_info_with_selenium(dlsite_brand_url)

            if tasks:
                results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                fetched_data = {key: res for key, res in zip(tasks.keys(), results) if not isinstance(res, Exception)}
                logging.info(f"✅ [品牌] '{brand_name}' 的新信息抓取完成。")

        brand_id = await finalize_brand_update(context, brand_name, brand_page_id, fetched_data)
        return {"brand_id": brand_id, "brand_name": brand_name}
    except Exception as e:
        logging.error(f"❌ [品牌] 处理品牌信息时出错: {e}")
        return {}


async def run_single_game_flow(context: dict) -> bool:
    """重构后的主流程，负责编排单个游戏的处理。"""
    try:
        # 阶段一：搜索与选择
        selection_result = await prompt_and_select_game(context)
        if selection_result is None: return False
        if selection_result == "retry": return True
        game, source, keyword, manual_mode = selection_result

        # 阶段二：重复项检查
        should_continue, selected_similar_page_id = await check_and_prepare_sync(context, game["title"])
        if not should_continue:
            return True

        # 阶段三：极致并发I/O操作
        logging.info("🚀 启动极致并发I/O任务...")
        loop = asyncio.get_running_loop()

        # 1. 立即启动所有不互相依赖的任务
        detail_task = loop.create_task(context[source].get_game_detail(game["url"]))
        ggbases_task = loop.create_task(_fetch_ggbases_data_cli(context, keyword, manual_mode))
        bangumi_task = loop.create_task(_fetch_bangumi_data_cli(context, keyword))

        # 2. 仅等待详情任务完成，以便触发依赖它的品牌任务
        logging.info("🔍 等待详情页数据以触发品牌抓取...")
        detail = await detail_task
        if not detail:
            logging.error(f"❌ 获取游戏 '{game['title']}' 的核心详情失败，流程终止。")
            ggbases_task.cancel()
            bangumi_task.cancel()
            return True
        detail["source"] = source
        logging.info("✅ 详情页数据已获取。")

        # 3. 详情获取后，立即启动品牌处理任务
        brand_task = loop.create_task(_fetch_and_process_brand_data_cli(context, detail, source))

        # 4. 等待所有剩余的后台任务完成
        logging.info("🔍 等待所有后台任务 (GGBases, Bangumi, Brand) 完成...")
        results = await asyncio.gather(ggbases_task, bangumi_task, brand_task, return_exceptions=True)
        logging.info("✅ 所有后台I/O任务均已完成！")

        # 5. 从结果中安全解包
        ggbases_result = results[0] if not isinstance(results[0], Exception) else {}
        bangumi_result = results[1] if not isinstance(results[1], Exception) else {}
        brand_data = results[2] if not isinstance(results[2], Exception) else {}

        ggbases_info = ggbases_result.get("info", {})
        selected_ggbases_game = ggbases_result.get("selected_game", {})
        bangumi_game_info = bangumi_result.get("game_info", {})
        bangumi_id = bangumi_result.get("bangumi_id")

        # 阶段四：数据处理与同步
        logging.info("🚀 所有数据已获取, 开始进行最终处理与同步...")
        created_page_id = await process_and_sync_game(
            game=game, detail=detail, notion_client=context["notion"], brand_id=brand_data.get("brand_id"),
            ggbases_client=context["ggbases"], user_keyword=keyword,
            notion_game_schema=context["schema_manager"].get_schema(GAME_DB_ID),
            tag_manager=context["tag_manager"], name_splitter=context["name_splitter"],
            interaction_provider=context["interaction_provider"],
            ggbases_detail_url=(selected_ggbases_game or {}).get("url"),
            ggbases_info=ggbases_info or {},
            ggbases_search_result=selected_ggbases_game or {},
            bangumi_info=bangumi_game_info, source=source,
            selected_similar_page_id=selected_similar_page_id,
        )

        # 阶段五：收尾工作
        if created_page_id and not selected_similar_page_id:
            # In-memory cache update with CLEAN title to ensure immediate de-duplication
            newly_created_page = await context["notion"].get_page(created_page_id)
            if newly_created_page:
                clean_title = context["notion"].get_page_title(newly_created_page)
                if clean_title:
                    new_game_entry = {"id": created_page_id, "title": clean_title}
                    context["cached_titles"].append(new_game_entry)
                    logging.info(f"🗂️ 实时查重缓存已更新: {clean_title}")

        if created_page_id and bangumi_id:
            await context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)

        logging.info(f"✅ 游戏 '{game['title']}' 处理流程完成！\n")

    except Exception as e:
        logging.error(f"❌ 处理流程出现严重错误: {e}")
        # The rich handler will print a beautifully formatted traceback automatically
        # so we don't need to print it manually anymore.
        pass

    return True  # 表示可以继续下一次循环


async def main():
    """程序主入口。"""
    context = await init_context()
    logging.info("🔧 [诊断] 准备创建品牌缓存预热后台任务...")
    asyncio.create_task(warm_up_brand_cache_standalone()) # 在后台预热品牌缓存
    logging.info("🔧 [诊断] 品牌缓存预热后台任务已创建。")
    try:
        while True:
            if not await run_single_game_flow(context):
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.warning("\n⚠️ 接收到中断信号，正在退出...")
    finally:
        logging.info("🔧 正在清理资源...")
        await close_context(context)
        logging.info("🔧 程序已安全退出。")


if __name__ == "__main__":
    setup_logging_for_cli()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🔍 程序被强制退出。")
