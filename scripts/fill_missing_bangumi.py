import difflib
import logging
import os
import re
import sys
import time
import unicodedata

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN as API_TOKEN
from config.config_token import CHARACTER_DB_ID, GAME_DB_ID, NOTION_TOKEN

HEADERS_API = {"Authorization": f"Bearer {API_TOKEN}", "User-Agent": "BangumiSync/1.0", "Accept": "application/json"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def normalize_title(title: str) -> str:
    if not title:
        return ""
    title = unicodedata.normalize("NFKC", title)
    title = title.replace("～", "〜").replace("’", "'")
    title = title.replace("“", '"').replace("”", '"')
    title = re.sub(r"[！!]", "!", title)
    title = re.sub(r"[ー─━―‐‑‒–—―]", "-", title)
    title = re.sub(r"\s+", "", title)
    return title.lower().strip()


def clean_title(title: str) -> str:
    title = re.sub(r"^【.*?】", "", title)
    title = re.sub(
        r"(通常版|体験版|豪華版|完全版|初回限定|限定版|特装版|Remake|HD Remaster|新装版|Premium|豪華絢爛版|デモ)",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip()


def simplify_title(title: str) -> str:
    return re.split(r"[-–~〜—―]", title)[0].strip()


def search_bangumi_id(keyword: str, try_simplify=True, similarity_threshold=0.75):
    def _search(key):
        url = "https://api.bgm.tv/v0/search/subjects"
        payload = {"keyword": key, "sort": "rank", "filter": {"type": [4], "nsfw": True}}
        resp = requests.post(url, headers=HEADERS_API, json=payload)
        if resp.status_code != 200:
            return None
        return resp.json().get("data", [])

    raw_results = _search(keyword)
    if not raw_results:
        if try_simplify:
            simplified = simplify_title(keyword)
            if simplified != keyword:
                return search_bangumi_id(simplified, try_simplify=False)
        return None

    norm_kw = normalize_title(keyword)
    best_match = None
    best_ratio = 0

    for item in raw_results:
        name = normalize_title(item.get("name", ""))
        name_cn = normalize_title(item.get("name_cn", ""))
        if norm_kw in name or norm_kw in name_cn:
            return str(item["id"])

        ratio = max(
            difflib.SequenceMatcher(None, norm_kw, name).ratio(),
            difflib.SequenceMatcher(None, norm_kw, name_cn).ratio(),
        )
        if ratio > best_ratio:
            best_match = item
            best_ratio = ratio

    if best_match and best_ratio >= similarity_threshold:
        logging.warning(f"⚠️ 相似度匹配成功：{best_match['name']}（相似度 {best_ratio:.2f}）")
        return str(best_match["id"])

    return None


def fetch_game(subject_id):
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
    r = requests.get(url, headers=HEADERS_API)
    if r.status_code != 200:
        return None
    d = r.json()
    return {
        "title": d.get("name"),
        "title_cn": d.get("name_cn"),
        "release_date": d.get("date"),
        "summary": d.get("summary", ""),
        "url": f"https://bangumi.tv/subject/{subject_id}",
    }


def fetch_characters(subject_id):
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
    r = requests.get(url, headers=HEADERS_API)
    if r.status_code != 200:
        return []

    characters = []
    for ch in r.json():
        char_id = ch["id"]
        detail = requests.get(f"https://api.bgm.tv/v0/characters/{char_id}", headers=HEADERS_API).json()
        stats = {i["key"]: i["value"] for i in detail.get("infobox", [])}
        if isinstance(stats.get("三围"), list):
            stats["三围"] = ", ".join([f"{i['k']}: {i['v']}" for i in stats["三围"]])

        aliases = set()
        if detail.get("name_cn"):
            aliases.add(detail["name_cn"])
        alias_raw = stats.get("别名") or stats.get("别称")
        if isinstance(alias_raw, str):
            aliases.update([a.strip() for a in re.split(r"[、,，/／；;]", alias_raw)])
        elif isinstance(alias_raw, list):
            for item in alias_raw:
                val = item["v"].strip() if isinstance(item, dict) else item.strip()
                aliases.add(val)

        characters.append(
            {
                "name": detail["name"],
                "cv": ch["actors"][0]["name"] if ch.get("actors") else "",
                "avatar": detail.get("images", {}).get("large", ""),
                "summary": detail.get("summary", "").strip(),
                "bwh": stats.get("三围", ""),
                "gender": stats.get("性别", ""),
                "url": f"https://bangumi.tv/character/{char_id}",
                "aliases": list(aliases),
            }
        )
    return characters


def is_character_existing(notion: NotionClient, url: str) -> str | None:
    query_url = f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query"
    payload = {"filter": {"property": "详情页面", "url": {"equals": url}}}
    resp = notion._request("POST", query_url, payload)
    results = resp.get("results", []) if resp else []
    return results[0]["id"] if results else None


def create_character_page(notion: NotionClient, char: dict):
    existing_id = is_character_existing(notion, char["url"])
    if existing_id:
        logging.info(f"⚠️ 已存在角色：{char['name']}")
        return existing_id

    props = {
        "角色名称": {"title": [{"text": {"content": char["name"]}}]},
        "详情页面": {"url": char["url"]},
    }

    if char.get("cv"):
        props["声优"] = {"rich_text": [{"text": {"content": char["cv"]}}]}
    if char.get("gender"):
        props["性别"] = {"select": {"name": char["gender"]}}
    if char.get("bwh"):
        props["BWH"] = {"rich_text": [{"text": {"content": char["bwh"]}}]}
    if char.get("summary"):
        props["简介"] = {"rich_text": [{"text": {"content": char["summary"]}}]}
    if char.get("avatar"):
        props["头像"] = {"files": [{"type": "external", "name": "avatar", "external": {"url": char["avatar"]}}]}
    if char.get("aliases"):
        alias_text = "、".join(char["aliases"][:20])
        props["别名"] = {"rich_text": [{"text": {"content": alias_text}}]}

    payload = {"parent": {"database_id": CHARACTER_DB_ID}, "properties": props}
    r = requests.post("https://api.notion.com/v1/pages", headers=notion.headers, json=payload)
    return r.json()["id"] if r.status_code == 200 else None


def get_games_missing_bangumi(notion: NotionClient):
    url = f"https://api.notion.com/v1/databases/{notion.game_db_id}/query"
    payload = {"filter": {"property": FIELDS["bangumi_url"], "url": {"is_empty": True}}, "page_size": 100}
    all_games = []
    next_cursor = None

    while True:
        if next_cursor:
            payload["start_cursor"] = next_cursor
        resp = notion._request("POST", url, payload)
        results = resp.get("results", []) if resp else []
        all_games.extend(results)
        if not resp or not resp.get("has_more"):
            break
        next_cursor = resp.get("next_cursor")

    return all_games


def clear_old_bangumi_data(notion: NotionClient, game_id: str):
    patch_payload = {
        "properties": {
            FIELDS["bangumi_url"]: {"url": None},
            FIELDS["game_characters"]: {"relation": []},
            FIELDS["voice_actor"]: {"multi_select": []},
        }
    }
    notion._request("PATCH", f"https://api.notion.com/v1/pages/{game_id}", patch_payload)


def run():
    notion = NotionClient(NOTION_TOKEN, GAME_DB_ID, CHARACTER_DB_ID)
    games = get_games_missing_bangumi(notion)
    logging.info(f"共找到 {len(games)} 个缺失 Bangumi 链接的游戏")

    unmatched_titles = []

    for game in games:
        try:
            props = game["properties"]
            title_raw = props[FIELDS["game_name"]]["title"][0]["text"]["content"]
            title = clean_title(title_raw)
            logging.info(f"🔍 正在处理游戏：{title_raw}")

            subject_id = search_bangumi_id(title)
            if not subject_id:
                logging.warning(f"❌ 未匹配：{title_raw}")
                clear_old_bangumi_data(notion, game["id"])
                unmatched_titles.append(title_raw)
                continue

            detail = fetch_game(subject_id)
            chars = fetch_characters(subject_id)

            character_relations = []
            all_cvs = set()
            for ch in chars:
                char_page_id = create_character_page(notion, ch)
                if char_page_id:
                    character_relations.append({"id": char_page_id})
                if ch.get("cv"):
                    all_cvs.add(ch["cv"].strip())
                time.sleep(0.3)

            patch = {
                FIELDS["bangumi_url"]: {"url": detail["url"]},
                FIELDS["game_characters"]: {"relation": character_relations},
            }
            if all_cvs:
                patch[FIELDS["voice_actor"]] = {"multi_select": [{"name": name} for name in sorted(all_cvs)]}

            notion._request("PATCH", f"https://api.notion.com/v1/pages/{game['id']}", {"properties": patch})
            logging.info(f"✅ 更新完成：{title_raw}")

        except Exception as e:
            logging.error(f"异常：{e}")
            unmatched_titles.append(title_raw)

    if unmatched_titles:
        with open("unmatched_games.txt", "w", encoding="utf-8") as f:
            for title in unmatched_titles:
                f.write(f"{title}\n")
        logging.warning(f"⚠️ 共 {len(unmatched_titles)} 个游戏未匹配，已写入 unmatched_games.txt")
    else:
        logging.info("🎉 所有游戏已成功匹配 Bangumi")


if __name__ == "__main__":
    run()
