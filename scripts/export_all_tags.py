#scripts/export_all_tags.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 添加项目根目录到模块路径
from notion_client import Client
from config.config_token import NOTION_TOKEN, GAME_DB_ID
from config.config_fields import FIELDS  # 包含标签字段名


# 初始化 Notion 客户端
notion = Client(auth=NOTION_TOKEN)

def get_all_games(database_id):
    all_results = []
    start_cursor = None
    while True:
        query = {
            "database_id": database_id,
            "page_size": 100,
        }
        if start_cursor:
            query["start_cursor"] = start_cursor
        response = notion.databases.query(**query)
        all_results.extend(response["results"])
        if response.get("has_more"):
            start_cursor = response["next_cursor"]
        else:
            break
    return all_results

def extract_all_tags(pages, tag_field_name):
    tag_set = set()
    for page in pages:
        try:
            tags = page["properties"][tag_field_name]["multi_select"]
            tag_set.update(tag["name"] for tag in tags)
        except Exception as e:
            continue  # 跳过无法解析的条目
    return sorted(tag_set)

def save_tags_to_txt(tags, filename="all_tags.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for tag in tags:
            f.write(tag + "\n")
    print(f"✅ 成功写入 {len(tags)} 个标签到 {filename}")

if __name__ == "__main__":
    print("📥 正在从 Notion 获取所有游戏记录...")
    pages = get_all_games(GAME_DB_ID)
    print(f"✅ 获取到 {len(pages)} 条记录")

    tag_field = FIELDS.get("标签", "标签")  # 从配置中读取字段名
    tags = extract_all_tags(pages, tag_field)
    save_tags_to_txt(tags)
