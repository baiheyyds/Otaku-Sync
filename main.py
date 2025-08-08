# main.py
import threading
import time
import warnings

from core.brand_handler import handle_brand_info
from core.game_processor import process_and_sync_game
from core.init import init_context
from core.selector import select_game
from utils.driver import create_driver
from utils.similarity_check import check_existing_similar_games, save_cache
from utils.utils import extract_main_keyword

warnings.filterwarnings("ignore", message=".*iCCP: known incorrect sRGB profile.*")


def main():
    context = init_context()

    notion = context["notion"]
    bangumi = context["bangumi"]
    dlsite = context["dlsite"]
    getchu = context["getchu"]
    ggbases = context["ggbases"]
    brand_cache = context["brand_cache"]
    brand_extra_info_cache = context["brand_extra_info_cache"]
    cached_titles = context["cached_titles"]

    driver = None
    try:
        while True:
            # 优化提示文本，让退出方式更清晰
            prompt_text = "\n请输入游戏关键词（日文，可加 -m 手动选择），或直接回车退出："
            keyword_raw = input(prompt_text).strip()
            if not keyword_raw:
                break

            interactive_mode = keyword_raw.endswith("-m")
            keyword = keyword_raw[:-2].strip() if interactive_mode else keyword_raw

            print(f"\n🔍 正在处理关键词: {keyword}")
            main_keyword = extract_main_keyword(keyword)
            print(f"🪄 提取主关键词: {main_keyword}")

            # --- 步骤 1: 选择游戏，支持取消 ---
            selected_game, source = select_game(dlsite, getchu, main_keyword, keyword)

            # 如果用户选择取消，则跳过本次循环
            if source == "cancel":
                print("🚫 操作已取消，请输入下一个关键词。")
                print("-" * 40)
                continue

            if not selected_game:
                print("❌ 未找到游戏，请重试。")
                continue

            selected_game["source"] = source
            print(f"✅ 选中游戏: {selected_game.get('title')} (来源: {source})")

            # --- 步骤 2: 获取基础信息并立即查重 ---
            print("🚀 (Phase 1) 正在通过Requests获取基础信息以供查重...")

            detail = {}
            if source == "dlsite":
                detail = dlsite.get_game_detail(selected_game["url"])
                print(f"✅ [Dlsite] (requests)抓取成功: 品牌={detail.get('品牌')}, 发售日={detail.get('发售日')}")
            else:
                detail = getchu.get_game_detail(selected_game["url"])
                detail.update(
                    {
                        "标题": selected_game.get("title"),
                        "品牌": detail.get("品牌") or selected_game.get("品牌"),
                        "链接": selected_game.get("url"),
                    }
                )
                print(f"✅ [Getchu] (requests)抓取成功: 品牌={detail.get('品牌')}, 发售日={detail.get('发售日')}")

            # 核心优化：在进行任何耗时操作前，先进行查重
            proceed, cached_titles, action, existing_page_id = check_existing_similar_games(
                notion, detail.get("标题") or selected_game.get("title"), cached_titles=cached_titles
            )
            if not proceed or action == "skip":
                print("-" * 40)
                continue

            # --- 步骤 3: 确认操作后，并发获取所有补充信息 ---
            print("🚀 (Phase 2) 确认操作，正在并发获取 Bangumi, GGBases 等补充信息...")

            # 用于存储所有线程的结果
            results = {
                "bangumi_info": {},
                "ggbases_info": {},
                "subject_id": None,
                "ggbases_detail_url": None,
            }

            # 定义并发函数
            def task_bangumi(keyword_for_search, results_dict):
                try:
                    subject_id = bangumi.search_and_select_bangumi_id(keyword_for_search.replace("-m", "").strip())
                    if subject_id:
                        results_dict["subject_id"] = subject_id
                        results_dict["bangumi_info"] = bangumi.fetch_game(subject_id)
                        print("🎯 [线程] Bangumi 游戏信息抓取成功")
                except Exception as e:
                    print(f"⚠️ [线程] Bangumi 游戏信息抓取异常: {e}")

            def task_ggbases(keyword_for_search, results_dict):
                try:
                    detail_url = ggbases.choose_or_parse_popular_url_with_requests(keyword_for_search)
                    if detail_url:
                        results_dict["ggbases_detail_url"] = detail_url
                except Exception as e:
                    print(f"⚠️ [线程] GGBases 搜索异常: {e}")

            # 启动并发任务
            threads = []
            bangumi_thread = threading.Thread(target=task_bangumi, args=(keyword_raw, results))
            threads.append(bangumi_thread)
            bangumi_thread.start()

            ggbases_thread = threading.Thread(target=task_ggbases, args=(keyword, results))
            threads.append(ggbases_thread)
            ggbases_thread.start()

            # 等待所有非Selenium线程完成
            for thread in threads:
                thread.join()

            # --- 按需启动 Selenium 执行耗时任务 ---
            print("🔩 (Phase 2.5) 检查是否需要启动Selenium获取补充信息...")
            ggbases_info = {}
            brand_extra_info = {}

            # 检查是否需要启动Selenium
            need_selenium = False
            brand_page_url = detail.get("品牌页链接")
            if results["ggbases_detail_url"]:
                need_selenium = True
            if source == "dlsite" and brand_page_url and brand_page_url not in brand_extra_info_cache:
                need_selenium = True

            if need_selenium:
                if driver is None:
                    print("...检测到需要Selenium，正在创建浏览器驱动...")
                    driver = create_driver()
                    dlsite.set_driver(driver)
                    ggbases.set_driver(driver)

                # 在需要时执行Selenium任务
                if results["ggbases_detail_url"]:
                    ggbases_info = ggbases.get_info_by_url_with_selenium(results["ggbases_detail_url"])

                if source == "dlsite" and brand_page_url and brand_page_url not in brand_extra_info_cache:
                    brand_extra_info = dlsite.get_brand_extra_info_with_selenium(brand_page_url)
                    if brand_extra_info.get("官网"):
                        brand_extra_info_cache[brand_page_url] = brand_extra_info

            # --- 步骤 4: 整合所有信息并同步到Notion ---
            print("🔄 (Phase 3) 整合所有信息并同步到Notion...")
            game_size = detail.get("容量") or ggbases_info.get("容量")
            print(f"📦 容量信息: {game_size or '未找到'}")

            brand_id = handle_brand_info(
                source=source,
                dlsite_client=dlsite,
                notion_client=notion,
                brand_name=detail.get("品牌"),
                brand_page_url=detail.get("品牌页链接") if source == "dlsite" else None,
                cache=brand_extra_info_cache,
                bangumi_client=bangumi,
                getchu_client=getchu,
                getchu_brand_page_url=detail.get("品牌官网") if source == "getchu" else None,
            )
            print(f"✅ 品牌信息同步完成，品牌ID: {brand_id}")

            bangumi_game_info = results.get("bangumi_info", {})
            notion_game_title = (
                bangumi_game_info.get("title") or bangumi_game_info.get("title_cn") or selected_game.get("title")
            )
            selected_game["notion_title"] = notion_game_title

            page_id = process_and_sync_game(
                selected_game,
                detail,
                game_size,
                notion,
                brand_id,
                ggbases,
                keyword,
                interactive=interactive_mode,
                ggbases_detail_url=results.get("ggbases_detail_url"),
                ggbases_info=ggbases_info,
                bangumi_info=bangumi_game_info,
                source=source,
                selected_similar_page_id=(existing_page_id if action == "update" else None),
            )

            if page_id and action == "create":
                cached_titles.append(
                    {"title": selected_game.get("title"), "id": page_id, "url": selected_game.get("url")}
                )
                save_cache(cached_titles)

            subject_id_final = results.get("subject_id")
            if subject_id_final:
                try:
                    game_page_id = existing_page_id if action == "update" else page_id
                    if not game_page_id:
                        search_results = notion.search_game(notion_game_title)
                        if search_results:
                            game_page_id = search_results[0].get("id")

                    if game_page_id:
                        print(f"🎭 抓取Bangumi角色数据...")
                        bangumi.create_or_link_characters(game_page_id, subject_id_final)
                    else:
                        print("⚠️ 未能确定游戏页面ID，跳过角色同步")
                except Exception as e:
                    print(f"⚠️ Bangumi角色补全异常: {e}")

            print(f"✅ 同步完成: {notion_game_title} {'(已覆盖更新)' if action == 'update' else '🎉'}")
            print("-" * 40)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n👋 用户中断，程序退出")
    finally:
        if driver:
            print("🚪 正在关闭浏览器驱动...")
            driver.quit()
        save_cache(cached_titles)
        brand_cache.save_cache(brand_extra_info_cache)
        print("♻️ 缓存和驱动已清理。程序结束。")


if __name__ == "__main__":
    main()
