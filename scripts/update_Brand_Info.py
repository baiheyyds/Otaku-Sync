import os
import sys
import time

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN, BRAND_DB_ID, NOTION_TOKEN
from utils.field_helper import (
    FIELD_ALIASES,
    extract_aliases,
    extract_first_valid,
    extract_link_map,
)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def query_all_brands():
    url = f"{NOTION_API_URL}/databases/{BRAND_DB_ID}/query"
    results = []
    next_cursor = None
    while True:
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        resp = requests.post(url, headers=HEADERS, json=payload).json()
        results.extend(resp.get("results", []))
        if resp.get("has_more"):
            next_cursor = resp.get("next_cursor")
        else:
            break
    return results


def extract_brand_name(notion_page):
    title_obj = notion_page["properties"][FIELDS["brand_name"]]["title"]
    return "".join(t["plain_text"] for t in title_obj).strip()


def bangumi_search_brand(keyword):
    url = "https://api.bgm.tv/v0/search/persons"
    headers = {
        "Authorization": f"Bearer {BANGUMI_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "OtakuNotionSync/1.0",
    }
    data = {"keyword": keyword, "filter": {"career": ["artist", "director", "producer"]}}
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code == 200:
        return resp.json().get("data", [])
    print(f"请求失败，状态码: {resp.status_code}")
    return []


def similarity_ratio(s1, s2):
    import difflib

    return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def extract_birthday(best_match):
    # 生日优先用字段，fallback用infobox
    if all(k in best_match for k in ("birth_year", "birth_mon", "birth_day")):
        s = str(best_match["birth_year"])
        if best_match["birth_mon"]:
            s += f"-{best_match['birth_mon']:02d}"
        if best_match["birth_day"]:
            s += f"-{best_match['birth_day']:02d}"
        return s
    birthday_keys = FIELD_ALIASES.get("brand_birthday", [])
    return extract_first_valid(best_match.get("infobox", []), birthday_keys)


def update_notion_brand(page_id, update_props):
    url = f"{NOTION_API_URL}/pages/{page_id}"
    resp = requests.patch(url, headers=HEADERS, json={"properties": update_props})
    return resp.status_code == 200


def main():
    print("🔍 获取品牌列表中...")
    brands = query_all_brands()
    print(f"共 {len(brands)} 个品牌")

    for i, brand in enumerate(brands, 1):
        brand_name = extract_brand_name(brand)
        page_id = brand["id"]
        print(f"\n[{i}/{len(brands)}] 查找 Bangumi 品牌：{brand_name}")

        results = bangumi_search_brand(brand_name)
        if not results:
            print("❌ 未找到匹配结果")
            continue

        # 找最相似结果
        best_match = None
        best_score = 0
        for r in results:
            names = [r.get("name", "")] + extract_aliases(r.get("infobox", []))
            score = max(similarity_ratio(brand_name, n) for n in names)
            if score > best_score:
                best_score = score
                best_match = r

        if best_score < 0.85:
            print(f"❌ 匹配度 {best_score:.2f} 太低，跳过")
            continue

        infobox = best_match.get("infobox", [])
        aliases = extract_aliases(infobox)
        links = extract_link_map(infobox)
        summary = best_match.get("summary", "")
        icon_url = best_match.get("img")
        birthday = extract_birthday(best_match)
        company_address = extract_first_valid(infobox, ["公司地址", "地址", "所在地", "所在地地址"])
        bangumi_url = f"https://bgm.tv/person/{best_match.get('id')}" if best_match.get("id") else None

        update_payload = {}

        if aliases:
            update_payload[FIELDS["brand_alias"]] = {"rich_text": [{"text": {"content": ", ".join(aliases)}}]}
        if links.get("官网"):
            update_payload[FIELDS["brand_official_url"]] = {"url": links["官网"]}
        if links.get("Ci-en"):
            update_payload[FIELDS["brand_cien"]] = {"url": links["Ci-en"]}
        if links.get("Twitter"):
            update_payload[FIELDS["brand_twitter"]] = {"url": links["Twitter"]}
        if summary:
            update_payload[FIELDS["brand_summary"]] = {"rich_text": [{"text": {"content": summary}}]}
        if icon_url:
            update_payload[FIELDS["brand_icon"]] = {
                "files": [{"type": "external", "name": "icon", "external": {"url": icon_url}}]
            }
        if birthday:
            update_payload[FIELDS["brand_birthday"]] = {"rich_text": [{"text": {"content": birthday}}]}
        if company_address:
            update_payload[FIELDS["brand_company_address"]] = {"rich_text": [{"text": {"content": company_address}}]}
        if bangumi_url:
            update_payload[FIELDS["brand_bangumi_url"]] = {"url": bangumi_url}

        if update_payload:
            if update_notion_brand(page_id, update_payload):
                print("✅ 品牌信息已更新")
            else:
                print("❌ 更新失败")
        else:
            print("⚠️ 无需更新信息")

        time.sleep(1.2)


if __name__ == "__main__":
    main()
