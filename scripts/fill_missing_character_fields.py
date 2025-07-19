import re
import time

import requests

from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN, CHARACTER_DB_ID, NOTION_TOKEN

HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

HEADERS_BANGUMI = {
    "Authorization": f"Bearer {BANGUMI_TOKEN}",
    "User-Agent": "BangumiSync/1.0",
    "Accept": "application/json",
}


def query_all_characters():
    url = f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query"
    has_more = True
    start_cursor = None
    results = []

    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = requests.post(url, headers=HEADERS_NOTION, json=payload)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def extract_bangumi_char_id(url):
    if not url:
        return None
    m = re.search(r"/character/(\d+)", url)
    return m.group(1) if m else None


def fetch_bangumi_character_detail(char_id):
    url = f"https://api.bgm.tv/v0/characters/{char_id}"
    resp = requests.get(url, headers=HEADERS_BANGUMI)
    if resp.status_code != 200:
        print(f"⚠️ 无法获取角色详情，ID={char_id}")
        return None
    return resp.json()


def parse_bwh_and_height(infobox):
    bwh = ""
    height = ""
    for info in infobox:
        key = info.get("key", "")
        val = info.get("value", "")
        if key in ("三围", "BWH"):
            bwh = val
        elif key == "身高":
            height = val
    return bwh, height


def parse_birthday_and_bloodtype(infobox):
    birthday = ""
    blood_type = ""
    for info in infobox:
        key = info.get("key", "")
        val = info.get("value", "")
        if key == "生日":
            birthday = val
        elif key == "血型":
            blood_type = val
    return birthday, blood_type


def update_character_props(page_id, bwh, height, birthday, blood_type):
    props = {}
    if bwh:
        props[FIELDS["character_bwh"]] = {"rich_text": [{"text": {"content": bwh}}]}
    if height:
        props[FIELDS["character_height"]] = {"rich_text": [{"text": {"content": height}}]}
    if birthday:
        props[FIELDS["character_birthday"]] = {"rich_text": [{"text": {"content": birthday}}]}
    if blood_type:
        # 血型是 select 类型，需要确保选项存在，否者更新失败
        props[FIELDS["character_blood_type"]] = {"select": {"name": blood_type}}

    if not props:
        return

    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": props}
    resp = requests.patch(url, headers=HEADERS_NOTION, json=payload)
    if resp.status_code == 200:
        print(f"✅ 更新成功：{page_id} BWH={bwh}, 身高={height}, 生日={birthday}, 血型={blood_type}")
    else:
        print(f"❌ 更新失败：{page_id} 状态码={resp.status_code} 内容={resp.text}")


def main():
    print("开始扫描角色数据库补充 BWH、身高、生日和血型字段...")
    characters = query_all_characters()
    print(f"共拉取到角色条目数: {len(characters)}")

    skipped = 0
    updated = 0

    for item in characters:
        try:
            page_id = item["id"]
            props = item.get("properties", {})

            def get_rich_text(prop_name):
                if prop_name in props and props[prop_name].get("rich_text"):
                    return props[prop_name]["rich_text"][0].get("text", {}).get("content", "").strip()
                return ""

            def get_select(prop_name):
                if prop_name in props and props[prop_name].get("select"):
                    return props[prop_name]["select"].get("name", "").strip()
                return ""

            # 先从 Notion 中取值
            bwh_val = get_rich_text(FIELDS["character_bwh"])
            height_val = get_rich_text(FIELDS["character_height"])
            birthday_val = get_rich_text(FIELDS["character_birthday"])
            blood_type_val = get_select(FIELDS["character_blood_type"])

            # ✅ 全部存在就跳过，无需访问 Bangumi
            if bwh_val and height_val and birthday_val and blood_type_val:
                skipped += 1
                continue

            detail_url = props.get(FIELDS["character_url"], {}).get("url")
            char_id = extract_bangumi_char_id(detail_url)
            if not char_id:
                print(f"⚠️ 无 Bangumi 角色ID，跳过: {page_id}")
                continue

            detail_json = fetch_bangumi_character_detail(char_id)
            if not detail_json:
                continue

            bwh_new, height_new = parse_bwh_and_height(detail_json.get("infobox", []))
            birthday_new, blood_type_new = parse_birthday_and_bloodtype(detail_json.get("infobox", []))

            # ✅ 仅当字段有变动时才 update
            if (
                (bwh_new and bwh_new != bwh_val)
                or (height_new and height_new != height_val)
                or (birthday_new and birthday_new != birthday_val)
                or (blood_type_new and blood_type_new != blood_type_val)
            ):
                update_character_props(page_id, bwh_new, height_new, birthday_new, blood_type_new)
                updated += 1

            time.sleep(0.2)  # 建议保留短暂 sleep，避免太快封IP
        except Exception as e:
            print(f"❌ 处理失败 {item.get('id')} 错误: {e}")

    print(f"\n扫描完成，共处理 {len(characters)} 个角色：")
    print(f"✅ 已更新: {updated}")
    print(f"⏩ 跳过无需更新的: {skipped}")


if __name__ == "__main__":
    main()
