import asyncio
import traceback
from PySide6.QtCore import QThread, Signal, QMutex, QWaitCondition

from utils import logger
from core.brand_handler import check_brand_status, finalize_brand_update
from core.game_processor import process_and_sync_game
from core.selector import search_all_sites, _find_best_match, SIMILARITY_THRESHOLD
from utils.similarity_check import find_similar_games_non_interactive
from config.config_token import GAME_DB_ID
from core.context_factory import create_loop_specific_context, create_shared_context
from utils.gui_bridge import GuiInteractionProvider


class GameSyncWorker(QThread):
    process_completed = Signal(bool)
    selection_required = Signal(list, str, str)
    duplicate_check_required = Signal(list)
    bangumi_mapping_required = Signal(dict)
    property_type_required = Signal(dict)
    context_created = Signal(dict)
    bangumi_selection_required = Signal(str, list)
    tag_translation_required = Signal(str, str)
    concept_merge_required = Signal(str, str)
    name_split_decision_required = Signal(str, list)
    confirm_brand_merge_requested = Signal(str, str)

    def __init__(self, keyword, manual_mode=False, parent=None, shared_context=None):
        super().__init__(parent)
        self.keyword = keyword
        self.manual_mode = manual_mode
        self.shared_context = shared_context
        self.context = {}
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        self.user_choice = None
        self.interaction_provider = None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def setup_context():
            """Create shared context if it doesn't exist, then create loop-specific context."""
            if not self.shared_context:
                logger.system("正在创建新的共享应用上下文...")
                self.shared_context = create_shared_context()
                self.context_created.emit(self.shared_context)
            
            self.interaction_provider = GuiInteractionProvider(loop)
            loop_specific_context = await create_loop_specific_context(
                self.shared_context, self.interaction_provider
            )
            self.context = {**self.shared_context, **loop_specific_context}

        try:
            # Run setup first to create the provider
            loop.run_until_complete(setup_context())

            # Then connect signals
            self.interaction_provider.handle_new_bangumi_key_requested.connect(self._on_bangumi_mapping_requested)
            self.interaction_provider.ask_for_new_property_type_requested.connect(self._on_property_type_requested)
            self.interaction_provider.select_bangumi_game_requested.connect(self._on_bangumi_selection_requested)
            self.interaction_provider.tag_translation_required.connect(self._on_tag_translation_requested)
            self.interaction_provider.concept_merge_required.connect(self._on_concept_merge_requested)
            self.interaction_provider.name_split_decision_required.connect(self._on_name_split_decision_requested)
            self.interaction_provider.confirm_brand_merge_requested.connect(self._on_brand_merge_requested)

            # Now run the main game flow
            loop.run_until_complete(self.game_flow())

        except Exception as e:
            logger.error(f"线程运行时出现致命错误: {e}")
            logger.error(traceback.format_exc())
            self.process_completed.emit(False)
        finally:
            if self.interaction_provider:
                try:
                    self.interaction_provider.handle_new_bangumi_key_requested.disconnect(self._on_bangumi_mapping_requested)
                    self.interaction_provider.ask_for_new_property_type_requested.disconnect(self._on_property_type_requested)
                    self.interaction_provider.select_bangumi_game_requested.disconnect(self._on_bangumi_selection_requested)
                    self.interaction_provider.tag_translation_required.disconnect(self._on_tag_translation_requested)
                    self.interaction_provider.concept_merge_required.disconnect(self._on_concept_merge_requested)
                    self.interaction_provider.name_split_decision_required.disconnect(self._on_name_split_decision_requested)
                    self.interaction_provider.confirm_brand_merge_requested.disconnect(self._on_brand_merge_requested)
                except RuntimeError:
                    pass

            async def cleanup_tasks():
                # Cancel background tasks first
                background_tasks = self.context.get("background_tasks", [])
                if background_tasks:
                    logger.system(f"正在取消 {len(background_tasks)} 个后台任务...")
                    for task in background_tasks:
                        task.cancel()
                    await asyncio.gather(*background_tasks, return_exceptions=True)
                    logger.system("所有后台任务已处理。")

                # Close HTTP client
                if self.context.get("async_client"):
                    await self.context["async_client"].aclose()
                    logger.system("线程内HTTP客户端已关闭。")

            if loop.is_running():
                loop.run_until_complete(cleanup_tasks())
            
            loop.close()

    def _on_bangumi_mapping_requested(self, request_data):
        self.bangumi_mapping_required.emit(request_data)

    def _on_property_type_requested(self, request_data):
        self.property_type_required.emit(request_data)

    def _on_bangumi_selection_requested(self, game_name, candidates):
        self.bangumi_selection_required.emit(game_name, candidates)

    def _on_tag_translation_requested(self, tag, source_name):
        self.tag_translation_required.emit(tag, source_name)

    def _on_concept_merge_requested(self, concept, candidate):
        self.concept_merge_required.emit(concept, candidate)

    def _on_name_split_decision_requested(self, text, parts):
        self.name_split_decision_required.emit(text, parts)

    def _on_brand_merge_requested(self, new_brand_name, suggested_brand):
        self.confirm_brand_merge_requested.emit(new_brand_name, suggested_brand)

    def set_interaction_response(self, response):
        if self.interaction_provider:
            self.interaction_provider.set_response(response)

    def set_choice(self, choice):
        self.mutex.lock()
        self.user_choice = choice
        self.mutex.unlock()
        self.wait_condition.wakeAll()

    async def wait_for_choice(self, choices: list, title: str, source: str = ""):
        # 1. 先发射信号，此时不持有任何锁，避免死锁
        if source:
            self.selection_required.emit(choices, title, source)
        else:
            self.duplicate_check_required.emit(choices)

        # 2. 现在获取锁，并等待主线程的响应
        self.mutex.lock()
        try:
            # 为等待用户输入设置60秒超时
            timed_out = not self.wait_condition.wait(self.mutex, 60000)
            if timed_out and self.user_choice is None:
                logger.warn("等待用户选择超时（60秒），将自动执行‘跳过’操作。")
                choice = "skip"
            else:
                choice = self.user_choice
        finally:
            # 3. 重置选择并解锁，为下一次交互做准备
            self.user_choice = None
            self.mutex.unlock()
        
        return choice

    async def _select_game_from_results(self, results, source):
        game = None
        while True:
            if not results:
                logger.warn(f"在 {source or '所有网站'} 未找到结果。")
                return None, source
            
            if not self.manual_mode:
                best_score, best_match = _find_best_match(self.keyword, results)
                if best_score >= SIMILARITY_THRESHOLD:
                    logger.info(f"[Selector] 智能模式自动选择 (相似度: {best_score:.2f}) -> {best_match['title']}")
                    game = best_match
                else:
                    logger.info(f"智能模式匹配度 ({best_score:.2f}) 过低，转为手动选择。")
            
            if game is None:
                choice = await self.wait_for_choice(results, f"请从 {source.upper()} 结果中选择", source)
                if choice == "search_fanza":
                    logger.info("切换到 Fanza 搜索...")
                    results, source = await search_all_sites(self.context["dlsite"], self.context["fanza"], self.keyword, site="fanza")
                    continue
                elif choice == -1 or choice is None:
                    logger.info("用户取消了选择。")
                    return None, source
                else:
                    game = results[choice]
            return game, source

    async def _check_for_duplicates(self, title):
        candidates, updated_cache = await find_similar_games_non_interactive(
            self.context["notion"], title, self.context["cached_titles"]
        )
        self.context["cached_titles"] = updated_cache
        if not candidates:
            return None
        
        choice = await self.wait_for_choice(candidates, "发现重复游戏")
        if choice == "skip":
            logger.info("已选择跳过。")
            return "skip"
        elif choice == "update":
            page_id = candidates[0][0].get("id")
            logger.info(f"已选择更新游戏：{candidates[0][0].get('title')}")
            return page_id
        elif choice == "create":
            logger.info("已选择强制创建新游戏。")
            return None
        return None

    async def _fetch_ggbases_data(self, keyword, manual_mode):
        logger.info("[GGBases] 开始获取 GGBases 数据...")
        try:
            candidates = await self.context["ggbases"].choose_or_parse_popular_url_with_requests(keyword)
            if not candidates:
                logger.warn("[GGBases] 未找到任何候选。")
                return {}

            selected_game = None
            if manual_mode:
                logger.info("[GGBases] 手动模式，需要用户选择。")
                choice = await self.wait_for_choice(candidates, "请从GGBases结果中选择", "ggbases")
                if isinstance(choice, int) and choice != -1:
                    selected_game = candidates[choice]
            else:
                selected_game = max(candidates, key=lambda x: x.get("popularity", 0))
            
            if not selected_game:
                logger.info("[GGBases] 用户未选择或无有效结果。")
                return {}

            logger.success(f"[GGBases] 已选择结果: {selected_game['title']}")
            url = selected_game.get("url")
            if not url:
                return {"selected_game": selected_game}

            driver = await self.context["driver_factory"].get_driver("ggbases_driver")
            if driver and not self.context["ggbases"].has_driver():
                self.context["ggbases"].set_driver(driver)
            
            info = await self.context["ggbases"].get_info_by_url_with_selenium(url)
            logger.success("[GGBases] Selenium 抓取完成。")
            return {"info": info, "selected_game": selected_game}
        except Exception as e:
            logger.error(f"[GGBases] 获取数据时出错: {e}")
            return {}

    async def _fetch_bangumi_data(self, keyword):
        logger.info("[Bangumi] 开始获取 Bangumi 数据...")
        try:
            bangumi_id = await self.context["bangumi"].search_and_select_bangumi_id(keyword)
            if not bangumi_id:
                logger.warn("[Bangumi] 未找到或未选择 Bangumi 条目。")
                return {}
            
            logger.info(f"[Bangumi] 已确定 Bangumi ID: {bangumi_id}, 正在获取详细信息...")
            game_info = await self.context["bangumi"].fetch_game(bangumi_id)
            logger.success("[Bangumi] 游戏详情获取完成。")
            return {"game_info": game_info, "bangumi_id": bangumi_id}
        except Exception as e:
            logger.error(f"[Bangumi] 获取数据时出错: {e}")
            return {}

    async def _fetch_and_process_brand_data(self, detail, source):
        logger.info("[品牌] 开始处理品牌信息...")
        try:
            raw_brand_name = detail.get("品牌")
            brand_name = self.context["brand_mapping_manager"].get_canonical_name(raw_brand_name)
            brand_page_id, needs_fetching = await check_brand_status(self.context, brand_name)
            
            fetched_data = {}
            if needs_fetching and brand_name:
                logger.step(f"品牌 '{brand_name}' 需要抓取新信息...")
                tasks = {}
                tasks["bangumi_brand_info"] = self.context["bangumi"].fetch_brand_info_from_bangumi(brand_name)
                
                dlsite_brand_url = detail.get("品牌页链接") if source == 'dlsite' else None
                if dlsite_brand_url and "/maniax/circle" in dlsite_brand_url:
                    driver = await self.context["driver_factory"].get_driver("dlsite_driver")
                    if driver and not self.context["dlsite"].has_driver():
                        self.context["dlsite"].set_driver(driver)
                    tasks["brand_extra_info"] = self.context["dlsite"].get_brand_extra_info_with_selenium(dlsite_brand_url)
                
                if tasks:
                    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                    fetched_data = {key: res for key, res in zip(tasks.keys(), results) if not isinstance(res, Exception)}
                    logger.success(f"[品牌] '{brand_name}' 的新信息抓取完成。")

            brand_id = await finalize_brand_update(self.context, brand_name, brand_page_id, fetched_data)
            return {"brand_id": brand_id, "brand_name": brand_name}
        except Exception as e:
            logger.error(f"[品牌] 处理品牌信息时出错: {e}")
            return {}

    async def game_flow(self) -> bool:
        try:
            # 阶段一：搜索与选择
            results, source = await search_all_sites(self.context["dlsite"], self.context["fanza"], self.keyword)
            game, source = await self._select_game_from_results(results, source)
            if not game:
                self.process_completed.emit(True)
                return True
            logger.info(f"已选择来源: {source.upper()}, 游戏: {game['title']}")

            # 阶段二：重复项检查
            selected_similar_page_id = await self._check_for_duplicates(game['title'])
            if selected_similar_page_id == 'skip':
                self.process_completed.emit(True)
                return True

            # 阶段三：极致并发I/O操作
            logger.info("启动极致并发I/O任务...")

            # 1. 立即启动所有不互相依赖的任务
            loop = asyncio.get_running_loop()
            detail_task = loop.create_task(self.context[source].get_game_detail(game["url"]))
            ggbases_task = loop.create_task(self._fetch_ggbases_data(self.keyword, self.manual_mode))
            bangumi_task = loop.create_task(self._fetch_bangumi_data(self.keyword))

            # 2. 仅等待详情任务完成，以便触发依赖它的品牌任务
            logger.info("等待详情页数据以触发品牌抓取...")
            detail = await detail_task
            if not detail:
                logger.error(f"获取游戏 '{game['title']}' 的核心详情失败，流程终止。")
                # 取消其他还在运行的任务
                ggbases_task.cancel()
                bangumi_task.cancel()
                self.process_completed.emit(False)
                return False
            detail["source"] = source
            logger.success("详情页数据已获取。")

            # 3. 详情获取后，立即启动品牌处理任务
            brand_task = loop.create_task(self._fetch_and_process_brand_data(detail, source))

            # 4. 等待所有剩余的后台任务完成
            logger.info("等待所有后台任务 (GGBases, Bangumi, Brand) 完成...")
            results = await asyncio.gather(ggbases_task, bangumi_task, brand_task, return_exceptions=True)
            logger.success("所有后台I/O任务均已完成！")

            # 5. 从结果中安全解包
            ggbases_result = results[0] if not isinstance(results[0], Exception) else {}
            bangumi_result = results[1] if not isinstance(results[1], Exception) else {}
            brand_data = results[2] if not isinstance(results[2], Exception) else {}

            ggbases_info = ggbases_result.get("info", {})
            selected_ggbases_game = ggbases_result.get("selected_game", {})
            bangumi_game_info = bangumi_result.get("game_info", {})
            bangumi_id = bangumi_result.get("bangumi_id")

            # 阶段四：数据处理与同步
            logger.info("所有数据已获取, 开始进行最终处理与同步...")
            created_page_id = await process_and_sync_game(
                game=game, detail=detail, notion_client=self.context["notion"], brand_id=brand_data.get("brand_id"),
                ggbases_client=self.context["ggbases"], user_keyword=self.keyword,
                notion_game_schema=self.context["schema_manager"].get_schema(GAME_DB_ID),
                tag_manager=self.context["tag_manager"],
                name_splitter=self.context["name_splitter"],
                interaction_provider=self.interaction_provider,
                ggbases_detail_url=(selected_ggbases_game or {}).get("url"),
                ggbases_info=ggbases_info or {},
                ggbases_search_result=selected_ggbases_game or {},
                bangumi_info=bangumi_game_info, source=source,
                selected_similar_page_id=selected_similar_page_id,
            )

            # 阶段五：收尾工作
            if created_page_id and not selected_similar_page_id:
                new_game_entry = {"id": created_page_id, "title": game["title"]}
                self.context["cached_titles"].append(new_game_entry)
                logger.cache(f"实时查重缓存已更新: {game['title']}")

            if created_page_id and bangumi_id:
                await self.context["bangumi"].create_or_link_characters(created_page_id, bangumi_id)

            logger.success(f"游戏 '{game['title']}' 处理流程完成！")
            self.process_completed.emit(True)
            return True

        except Exception as e:
            logger.error(f"处理流程出现严重错误: {e}")
            logger.error(traceback.format_exc())
            self.process_completed.emit(False)
            return False

class ScriptWorker(QThread):
    script_completed = Signal(str, bool, object)
    context_created = Signal(dict)

    def __init__(self, script_function, script_name, parent=None, shared_context=None):
        super().__init__(parent)
        self.script_function = script_function
        self.script_name = script_name
        self.shared_context = shared_context
        self.context = {}
        self.interaction_provider = None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = None

        async def setup_context():
            if not self.shared_context:
                logger.system("正在为脚本运行创建新的共享应用上下文...")
                self.shared_context = create_shared_context()
                self.context_created.emit(self.shared_context)
            
            self.interaction_provider = GuiInteractionProvider(loop)
            loop_specific_context = await create_loop_specific_context(
                self.shared_context, self.interaction_provider
            )
            self.context = {**self.shared_context, **loop_specific_context}

        try:
            loop.run_until_complete(setup_context())
            # Connect signals for interactive scripts
            self.interaction_provider.tag_translation_required.connect(self.parent().handle_tag_translation_required)
            self.interaction_provider.concept_merge_required.connect(self.parent().handle_concept_merge_required)
            self.interaction_provider.handle_new_bangumi_key_requested.connect(self.parent().handle_bangumi_mapping)
            self.interaction_provider.ask_for_new_property_type_requested.connect(self.parent().handle_property_type)
            self.interaction_provider.select_bangumi_game_requested.connect(self.parent().handle_bangumi_selection_required)
            self.interaction_provider.name_split_decision_required.connect(self.parent().handle_name_split_decision_required)

            # Set drivers for clients that need them
            driver_keys = ["dlsite_driver", "ggbases_driver"]
            for key in driver_keys:
                driver = loop.run_until_complete(self.context["driver_factory"].get_driver(key))
                if driver:
                    if key == "dlsite_driver":
                        self.context["dlsite"].set_driver(driver)
                    elif key == "ggbases_driver":
                        self.context["ggbases"].set_driver(driver)

            logger.system(f"后台线程开始执行脚本: {self.script_name}")
            # Pass the entire context, which now includes the interaction_provider
            awaitable_func = self.script_function(self.context)
            result = loop.run_until_complete(awaitable_func)
            logger.success(f"脚本 {self.script_name} 执行完毕。")
            self.script_completed.emit(self.script_name, True, result)

        except Exception as e:
            logger.error(f"脚本 {self.script_name} 执行时出现致命错误: {e}")
            logger.error(traceback.format_exc())
            self.script_completed.emit(self.script_name, False, None)
        finally:
            # Disconnect signals
            if self.interaction_provider:
                try:
                    self.interaction_provider.tag_translation_required.disconnect(self.parent().handle_tag_translation_required)
                    self.interaction_provider.concept_merge_required.disconnect(self.parent().handle_concept_merge_required)
                    self.interaction_provider.handle_new_bangumi_key_requested.disconnect(self.parent().handle_bangumi_mapping)
                    self.interaction_provider.ask_for_new_property_type_requested.disconnect(self.parent().handle_property_type)
                    self.interaction_provider.select_bangumi_game_requested.disconnect(self.parent().handle_bangumi_selection_required)
                    self.interaction_provider.name_split_decision_required.disconnect(self.parent().handle_name_split_decision_required)
                except (RuntimeError, TypeError):
                    pass # Ignore errors on disconnect

            async def cleanup_tasks():
                # Cancel background tasks first
                background_tasks = self.context.get("background_tasks", [])
                if background_tasks:
                    logger.system(f"正在取消 {len(background_tasks)} 个后台任务...")
                    for task in background_tasks:
                        task.cancel()
                    await asyncio.gather(*background_tasks, return_exceptions=True)
                    logger.system("所有后台任务已处理。")

                # Close HTTP client
                if self.context.get("async_client"):
                    await self.context["async_client"].aclose()
                    logger.system("脚本线程内的HTTP客户端已关闭。")

            if loop.is_running():
                loop.run_until_complete(cleanup_tasks())
            
            loop.close()