import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import requests
import config.config_token as config

# 从 config 中提取所有以 _DB_ID 结尾的变量
def list_database_ids():
    db_ids = {}
    for key in dir(config):
        if key.endswith("_DB_ID"):
            db_ids[key] = getattr(config, key)
    return db_ids

def get_database_properties(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}"
    headers = {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ 获取失败，HTTP {resp.status_code}：{resp.text}")
        return

    data = resp.json()
    properties = data.get("properties", {})

    print("\n📘 数据库字段信息如下：\n")
    for name, prop in properties.items():
        prop_type = prop.get("type", "未知")
        print(f"🔹 字段名: {name}")
        print(f"   类型: {prop_type}")
        print("-" * 40)

if __name__ == "__main__":
    db_map = list_database_ids()

    print("📂 请选择要查看的数据库：\n")
    options = list(db_map.items())
    for idx, (name, _) in enumerate(options, 1):
        print(f"[{idx}] {name}")

    choice = input("\n请输入编号：").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
        print("❌ 输入无效")
        sys.exit(1)

    db_key, db_id = options[int(choice) - 1]
    print(f"\n🔍 正在查询 {db_key}...\n")
    get_database_properties(db_id)
