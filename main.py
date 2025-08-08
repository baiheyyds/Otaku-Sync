# main.py
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
            keyword_raw = input("\n请输入游戏关键词（日文，可加 -m 手动选择 GGBases，回车退出）：").strip()
            if not keyword_raw:
                break

            interactive_mode = keyword_raw.endswith("-m")
            keyword = keyword_raw[:-2].strip() if interactive_mode else keyword_raw

            print(f"\n🔍 正在处理关键词: {keyword}")
            main_keyword = extract_main_keyword(keyword)
            print(f"🪄 提取主关键词: {main_keyword}")

            selected_game, source = select_game(dlsite, getchu, main_keyword, keyword)
            if not selected_game:
                print("❌ 未找到游戏，请重试。")
                continue

            selected_game["source"] = source
            print(f"✅ 选中游戏: {selected_game.get('title')} (来源: {source})")

            # --- Phase 1: Requests-based info gathering ---
            print("🚀 (Phase 1) 正在通过Requests获取基础信息...")

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

            bangumi_info = {}
            subject_id = None
            try:
                subject_id = bangumi.search_and_select_bangumi_id(keyword_raw.replace("-m", "").strip())
                if subject_id:
                    bangumi_info = bangumi.fetch_game(subject_id)
                    print(f"🎯 Bangumi 游戏封面图抓取成功: {bangumi_info.get('封面图链接')}")
            except Exception as e:
                print(f"⚠️ Bangumi 游戏信息抓取异常: {e}")

            proceed, cached_titles, action, existing_page_id = check_existing_similar_games(
                notion, detail.get("标题") or selected_game.get("title"), cached_titles=cached_titles
            )
            if not proceed or action == "skip":
                continue

            # --- Phase 2: Selenium-based supplementary info gathering ---
            print("🔩 (Phase 2) 检查是否需要启动Selenium获取补充信息...")
            ggbases_info = {}
            detail_url = ggbases.choose_or_parse_popular_url_with_requests(keyword)
            if detail_url:
                if driver is None:
                    print("...首次需要，正在创建浏览器驱动...")
                    driver = create_driver()
                    dlsite.set_driver(driver)
                    ggbases.set_driver(driver)
                ggbases_info = ggbases.get_info_by_url_with_selenium(detail_url)

            brand_page_url = detail.get("品牌页链接")
            if source == "dlsite" and brand_page_url and brand_page_url not in brand_extra_info_cache:
                if driver is None:
                    print("...首次需要，正在创建浏览器驱动...")
                    driver = create_driver()
                    dlsite.set_driver(driver)
                    ggbases.set_driver(driver)

                brand_extra_info = dlsite.get_brand_extra_info_with_selenium(brand_page_url)
                if brand_extra_info.get("官网"):
                    brand_extra_info_cache[brand_page_url] = brand_extra_info

            # --- Phase 3: Data processing and syncing ---
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

            notion_game_title = bangumi_info.get("title") or bangumi_info.get("title_cn") or selected_game.get("title")
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
                ggbases_detail_url=detail_url,
                ggbases_info=ggbases_info,
                bangumi_info=bangumi_info,
                source=source,
                selected_similar_page_id=(existing_page_id if action == "update" else None),
            )

            if page_id and action == "create":
                cached_titles.append(
                    {"title": selected_game.get("title"), "id": page_id, "url": selected_game.get("url")}
                )
                save_cache(cached_titles)

            if subject_id:
                try:
                    game_page_id = existing_page_id if action == "update" else page_id
                    if not game_page_id:
                        search_results = notion.search_game(notion_game_title)
                        if search_results:
                            game_page_id = search_results[0].get("id")

                    if game_page_id:
                        print(f"🎭 抓取Bangumi角色数据...")
                        bangumi.create_or_link_characters(game_page_id, subject_id)
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
