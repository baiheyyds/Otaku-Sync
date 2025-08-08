# core/init.py
import threading

from clients.bangumi_client import BangumiClient
from clients.brand_cache import BrandCache
from clients.dlsite_client import DlsiteClient
from clients.getchu_client import GetchuClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from utils.similarity_check import hash_titles, load_cache_quick, save_cache


def update_cache_background(notion_client, local_cache):
    try:
        print("🔄 正在后台刷新查重缓存...")
        remote_data = notion_client.get_all_game_titles()
        print(f"🔄 后台拉取的远程游戏标题数量: {len(remote_data)}")

        local_hash = hash_titles(local_cache)
        remote_hash = hash_titles(remote_data)
        if local_hash != remote_hash:
            if remote_data:
                print("♻️ Notion 游戏标题有更新，已刷新缓存")
                save_cache(remote_data)
            else:
                print("⚠️ 拉取到的远程缓存为空，跳过保存以避免清空本地缓存")
        else:
            print("✅ 游戏标题缓存已是最新")
    except Exception as e:
        print(f"⚠️ 后台更新缓存失败: {e}")


def init_context():
    print("\n🚀 启动程序...")

    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID)
    bangumi = BangumiClient(notion)
    dlsite = DlsiteClient()
    getchu = GetchuClient()
    ggbases = GGBasesClient()

    brand_cache = BrandCache()
    brand_extra_info_cache = brand_cache.load_cache()
    cached_titles = load_cache_quick()
    print(f"🗂️ 本地缓存游戏条目数: {len(cached_titles)}")

    threading.Thread(target=update_cache_background, args=(notion, cached_titles), daemon=True).start()

    return {
        "driver": None,
        "notion": notion,
        "bangumi": bangumi,
        "dlsite": dlsite,
        "getchu": getchu,
        "ggbases": ggbases,
        "brand_cache": brand_cache,
        "brand_extra_info_cache": brand_extra_info_cache,
        "cached_titles": cached_titles,
    }
