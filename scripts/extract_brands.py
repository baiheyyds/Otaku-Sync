import requests
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config_token import NOTION_TOKEN, BRAND_DB_ID

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def query_all_brand_names():
    url = f"https://api.notion.com/v1/databases/{BRAND_DB_ID}/query"
    all_names = set()
    next_cursor = None

    print("🔍 正在读取品牌数据库条目...")

    while True:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor

        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print("❌ 请求失败:", response.text)
            break

        data = response.json()
        for page in data.get("results", []):
            prop = page["properties"].get("厂商名")
            if prop and prop["type"] == "title":
                name = "".join([t["text"]["content"] for t in prop["title"]])
                if name:
                    all_names.add(name)

        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break

        time.sleep(0.3)

    return sorted(all_names)

def main():
    brand_names = query_all_brand_names()
    with open("brand_names.txt", "w", encoding="utf-8") as f:
        for name in brand_names:
            f.write(name + "\n")

    print(f"✅ 已写入 {len(brand_names)} 个品牌名到 brand_names.txt")

if __name__ == "__main__":
    main()
