# main.py
import os
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*iCCP: known incorrect sRGB profile.*")


from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.getchu_client import GetchuClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from core.brand_handler import handle_brand_info
from core.game_processor import process_and_sync_game
from core.selector import select_game
from utils.similarity_check import check_existing_similar_games, load_cache, save_cache
from utils.utils import extract_main_keyword

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# 设置缓存目录
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 设置缓存文件路径（确保 similarity_check 使用同样路径）
CACHE_PATH = CACHE_DIR / "game_titles_cache.json"


def create_shared_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    log_path = "NUL" if os.name == "nt" else "/dev/null"
    service = Service(log_path=log_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1200, 800)
    return driver


def main():
    print("\n🚀 启动程序，创建浏览器驱动...")
    driver = create_shared_driver()
    print("✅ 浏览器驱动创建完成。")

    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID)
    bangumi = BangumiClient(notion)
    dlsite = DlsiteClient(driver=driver)
    getchu = GetchuClient(driver=driver)
    ggbases = GGBasesClient(driver=driver)
    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()

    cached_titles = load_cache(notion_client=notion)
    print(f"🗂️ 已加载缓存游戏条目数: {len(cached_titles)}")

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

            # 只调用一次 Bangumi 搜索
            subject_id = None
            bangumi_info = {}
            try:
                # 使用用户原始输入的关键词进行搜索，而不是 selected_game["title"]
                subject_id = bangumi.search_and_select_bangumi_id(keyword_raw.replace("-m", "").strip())
                if subject_id:
                    bangumi_info = bangumi.fetch_game(subject_id)
                    print(f"🎯 Bangumi 游戏封面图抓取成功: {bangumi_info.get('封面图链接')}")
                else:
                    print("⚠️ Bangumi 未匹配到对应游戏")
            except Exception as e:
                print(f"⚠️ Bangumi 游戏信息抓取异常: {e}")

            proceed, cached_titles, action, existing_page_id = check_existing_similar_games(
                notion, selected_game.get("title"), cached_titles=cached_titles
            )
            if not proceed or action == "skip":
                continue

            if source == "dlsite":
                detail = dlsite.get_game_detail(selected_game["url"])
                print(f"✅ [Dlsite] 抓取成功: 品牌={detail.get('品牌')}, 发售日={detail.get('发售日')} ✔️")
            else:
                detail = getchu.get_game_detail(selected_game["url"])
                detail.update(
                    {
                        "标题": selected_game.get("title"),
                        "品牌": detail.get("品牌") or selected_game.get("品牌"),
                        "链接": selected_game.get("url"),
                    }
                )
                print(f"✅ [Getchu] 抓取成功: 品牌={detail.get('品牌')}, 发售日={detail.get('发售日')} ✔️")
                if not detail.get("作品形式"):
                    detail["作品形式"] = ["ADV", "有声音", "有音乐"]

            html = ggbases.get_search_page_html(keyword)
            detail_url = ggbases.choose_or_parse_popular_url(html, interactive=interactive_mode)
            ggbases_info = ggbases.get_info_by_url(detail_url) if detail_url else {}

            if source == "getchu":
                game_size = ggbases_info.get("容量") or detail.get("容量")
                if ggbases_info.get("容量"):
                    print(f"📦 [GGBases] 容量信息: {game_size}")
                elif detail.get("容量"):
                    print(f"📦 GGBases暂无资源，[原始数据] 容量信息: {game_size}")
                else:
                    print(f"⚠️ 未找到任何容量信息")
            else:
                game_size = detail.get("容量") or ggbases_info.get("容量")
                if detail.get("容量"):
                    print(f"📦 [Dlsite] 容量信息: {game_size}")
                elif ggbases_info.get("容量"):
                    print(f"📦 Dlsite无大小信息，[GGBases] 容量信息: {game_size}")
                else:
                    print(f"⚠️ 未找到任何容量信息")

            if source == "getchu":
                if ggbases_info.get("封面图链接"):
                    detail["封面图链接"] = ggbases_info["封面图链接"]
                    print("🖼️ 使用 GGBases 封面图替代原封面")
                else:
                    print("⚠️ 未找到 GGBases 封面图")
            else:
                if ggbases_info.get("封面图链接"):
                    print("🖼️ GGBases 有封面图，但 dlsite 源不覆盖封面图，继续用 dlsite 原封面")

            print("🔍 品牌信息处理...")
            brand_name = detail.get("品牌") or selected_game.get("品牌")

            # 这里要根据来源传入对应的品牌页 URL
            brand_url = None  # Dlsite 品牌页链接
            getchu_brand_url = None  # Getchu 品牌页链接

            if source == "dlsite":
                brand_url = detail.get("品牌页链接")
            elif source == "getchu":
                getchu_brand_url = detail.get("品牌页链接")

            brand_homepage = None  # 不直接赋值，交给 handle_brand_info 判断

            brand_id = handle_brand_info(
                source=source,
                dlsite_client=dlsite,
                notion_client=notion,
                brand_name=brand_name,
                brand_page_url=brand_url,
                cache=brand_extra_info_cache,
                brand_homepage=brand_homepage,
                brand_icon=detail.get("品牌图标"),
                bangumi_client=bangumi,
                getchu_client=getchu,
                getchu_brand_page_url=getchu_brand_url,
            )

            print(f"✅ 品牌信息同步完成，品牌ID: {brand_id}")

            page_id_for_update = existing_page_id if action == "update" else None

            print(f"📤 开始同步游戏数据到 Notion...")
            notion_game_title = bangumi_info.get("title") or bangumi_info.get("title_cn") or selected_game.get("title")
            selected_game["notion_title"] = notion_game_title

            # 调用游戏处理函数，获得创建或更新的页面ID
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
                selected_similar_page_id=page_id_for_update,
            )

            # 新建时更新缓存
            if page_id and action == "create":
                cached_titles.append({
                    "title": selected_game.get("title"),
                    "id": page_id,
                    "url": selected_game.get("url"),
                })
                save_cache(cached_titles)

            # Bangumi角色同步
            try:
                if subject_id:
                    print(f"🎭 抓取Bangumi角色数据...")
                    game_page_id = existing_page_id if action == "update" else None

                    if not game_page_id:
                        search_results = notion.search_game(selected_game.get("notion_title"))
                        if search_results:
                            game_page_id = search_results[0].get("id")

                    if game_page_id:
                        bangumi.create_or_link_characters(game_page_id, subject_id)
                    else:
                        print("⚠️ 未能确定游戏页面ID，跳过角色同步")
                else:
                    print("⚠️ Bangumi匹配失败，跳过角色补全")

            except Exception as e:
                print(f"⚠️ Bangumi角色补全异常: {e}")

            if action == "update":
                print(f"🔁 已覆盖更新原条目")
            else:
                print(f"✅ 游戏同步完成: {notion_game_title} 🎉")

            print("-" * 40)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n👋 用户中断，程序退出")
    finally:
        save_cache(cached_titles)  # 保存游戏标题缓存
        brand_cache.save_cache(brand_extra_info_cache)
        print("♻️ 品牌缓存已保存")
        driver.quit()
        print("🚪 浏览器驱动已关闭")


if __name__ == "__main__":
    main()
