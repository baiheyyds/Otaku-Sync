# scripts/auto_tag_completer.py
import warnings

warnings.filterwarnings("ignore")
import os
import sys

sys.stderr = open(os.devnull, "w")

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.dlsite_client import DlsiteClient
from clients.ggbases_client import GGBasesClient
from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BRAND_DB_ID, GAME_DB_ID, NOTION_TOKEN
from utils.tag_logger import append_new_tags
from utils.tag_mapping import map_and_translate_tags

TAG_JP_PATH = "mapping/tag_jp_to_cn.json"  # 路径统一处理


def load_tag_jp_to_cn():
    if not os.path.exists(TAG_JP_PATH):
        return {}
    with open(TAG_JP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_tags_from_dlsite(url):
    client = DlsiteClient()
    try:
        detail = client.get_game_detail(url)
        tags = detail.get("标签", [])
        return tags if isinstance(tags, list) else []
    except Exception as e:
        print(f"❌ 获取 DLsite 标签失败: {e}")
        return []


def get_tags_from_ggbase(url):
    client = GGBasesClient()
    try:
        info = client.get_info_by_url(url)
        tags = info.get("标签", [])
        return tags if isinstance(tags, list) else []
    except Exception as e:
        print(f"❌ 获取 GGBases 标签失败: {e}")
        return []


def check_missing_mappings(tags, mapping_dict):
    return [tag for tag in tags if tag not in mapping_dict]


def main():
    print("🛠️ 开始批量补全标签...")
    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID)
    dlsite_client = DlsiteClient()
    ggbases_client = GGBasesClient()

    query_url = f"https://api.notion.com/v1/databases/{GAME_DB_ID}/query"
    payload = {"filter": {"property": FIELDS["tags"], "multi_select": {"is_empty": True}}}

    results = notion._request("POST", query_url, payload)
    if not results:
        print("❌ 无法获取游戏数据")
        return

    games = results.get("results", [])
    total = len(games)

    for idx, page in enumerate(games, start=1):
        props = page["properties"]
        title = props[FIELDS["game_name"]]["title"][0]["text"]["content"]
        print(f"\n🕵️‍♂️ 处理游戏 {idx}/{total}：{title}")

        dlsite_url = props.get(FIELDS["game_url"], {}).get("url")
        ggbases_url = props.get(FIELDS["resource_link"], {}).get("url")

        raw_dlsite_tags = []
        raw_ggbase_tags = []

        if dlsite_url and "dlsite.com" in dlsite_url:
            raw_dlsite_tags = get_tags_from_dlsite(dlsite_url)
        elif dlsite_url and "getchu.com" in dlsite_url:
            print("🔕 Getchu 入正链接，跳过标签抓取")

        if ggbases_url:
            raw_ggbase_tags = get_tags_from_ggbase(ggbases_url)

        # 🛑 检测是否有未映射的 DLsite 标签
        jp_cn_map = load_tag_jp_to_cn()
        missing_mappings = check_missing_mappings(raw_dlsite_tags, jp_cn_map)

        if missing_mappings:
            print("⛔ 检测到以下 DLsite 标签没有在 tag_jp_to_cn.json 中映射：")
            for t in missing_mappings:
                print("   🔹", t)

            added = append_new_tags(TAG_JP_PATH, missing_mappings)
            if added:
                print("🆕 新增 DLsite 标签已写入 tag_jp_to_cn.json")

            print("⏭️  跳过当前游戏，不提交任何标签到 Notion。")
            continue  # 跳过该游戏，不做标签提交

        # 标签处理：映射 + 合并
        mapped_dlsite = map_and_translate_tags(raw_dlsite_tags, source="dlsite")
        mapped_ggbase = map_and_translate_tags(raw_ggbase_tags, source="ggbase")
        final_tags = sorted(set(mapped_dlsite + mapped_ggbase))

        if not final_tags:
            print("🚫 没有可补充的标签")
            continue

        # 更新标签映射文件（仅 GGBase 标签）
        if append_new_tags("mapping/tag_ggbase.json", raw_ggbase_tags):
            print("🆕 新增 GGBase 标签已写入映射文件")

        # 提交到 Notion
        update_url = f"https://api.notion.com/v1/pages/{page['id']}"
        payload = {"properties": {FIELDS["tags"]: {"multi_select": [{"name": tag} for tag in final_tags]}}}

        notion._request("PATCH", update_url, payload)


if __name__ == "__main__":
    main()
