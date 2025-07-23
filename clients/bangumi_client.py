# clients/bangumi_client.py
# 该模块用于与 Bangumi API 交互，获取游戏和角色信息
import difflib
import json
import logging
import os
import re
import time
import unicodedata

import requests

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN, CHARACTER_DB_ID
from utils.field_helper import extract_aliases, extract_first_valid, extract_link_map

API_TOKEN = BANGUMI_TOKEN
HEADERS_API = {
    "Authorization": f"Bearer {API_TOKEN}",
    "User-Agent": "BangumiSync/1.0",
    "Accept": "application/json",
}

# 加载字段别名配置
alias_path = os.path.join(os.path.dirname(__file__), "../config/field_aliases.json")
with open(alias_path, "r", encoding="utf-8") as f:
    FIELD_ALIASES = json.load(f)

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

def extract_primary_brand_name(name: str) -> str:
    """
    提取品牌名中的主干部分，忽略括号中的读音/注音。
    如：'SUKARADOG（スカラドギ）' → 'SUKARADOG'
    """
    if not name:
        return name
    # 删除中文或英文括号中的内容
    name = re.sub(r"[（(].*?[）)]", "", name)
    return name.strip()


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


class BangumiClient:
    def __init__(self, notion: NotionClient):
        self.notion = notion
        self.headers = HEADERS_API
        self.similarity_threshold = 0.85

    def _search(self, keyword: str):
        url = "https://api.bgm.tv/v0/search/subjects"
        payload = {
            "keyword": keyword,
            "sort": "rank",
            "filter": {"type": [4], "nsfw": True},
        }
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code != 200:
            return []
        return resp.json().get("data", [])

    def search_and_select_bangumi_id(self, keyword: str) -> str | None:
        raw_results = self._search(keyword)
        if not raw_results:
            simplified = simplify_title(keyword)
            if simplified != keyword:
                raw_results = self._search(simplified)
            if not raw_results:
                return None

        # 预处理关键词
        norm_kw = normalize_title(keyword)
        clean_kw = normalize_title(clean_title(keyword))
        simp_kw = normalize_title(simplify_title(keyword))

        candidates = []
        for item in raw_results:
            name = item.get("name", "")
            name_cn = item.get("name_cn", "")
            norm_name = normalize_title(name)
            norm_cn = normalize_title(name_cn)

            # 计算多个方式的最大相似度
            ratios = [
                difflib.SequenceMatcher(None, norm_kw, norm_name).ratio(),
                difflib.SequenceMatcher(None, clean_kw, normalize_title(clean_title(name))).ratio(),
                difflib.SequenceMatcher(None, simp_kw, normalize_title(simplify_title(name))).ratio(),
                difflib.SequenceMatcher(None, norm_kw, norm_cn).ratio(),
            ]
            max_ratio = max(ratios)
            candidates.append((max_ratio, item))

        candidates.sort(key=lambda x: x[0], reverse=True)

        # 子串匹配（更严格，只允许候选标题包含关键词）
        for _, item in candidates:
            item_clean = clean_title(item.get("name", ""))
            keyword_clean = clean_title(keyword)
            # 只允许关键词是子串，候选标题包含关键词才匹配
            if item_clean and (keyword_clean in item_clean):
                logging.info(f"子串匹配成功：{item['name']}，视为同一作品")
                return str(item["id"])


        # ✅ 相似度 ≥ 阈值
        if candidates and candidates[0][0] >= self.similarity_threshold:
            best = candidates[0][1]
            logging.info(f"自动匹配 Bangumi: {best['name']}（相似度 {candidates[0][0]:.2f}）")
            return str(best["id"])

        # ✅ 宽松匹配：标题包含或相似度稍低
        if candidates and candidates[0][0] >= 0.7:
            best = candidates[0][1]
            if clean_title(best["name"]) in clean_title(keyword) or clean_title(keyword) in clean_title(best["name"]):
                logging.info(f"模糊匹配 Bangumi（放宽判定）: {best['name']}（相似度 {candidates[0][0]:.2f}）")
                return str(best["id"])

        # ❌ 无法自动匹配，转手动选择
        print("⚠️ Bangumi自动匹配相似度不足，请手动选择:")
        for idx, (ratio, item) in enumerate(candidates[:10]):
            print(f"{idx + 1}. {item['name']} / {item.get('name_cn','')} (相似度: {ratio:.2f})")
        print("0. 放弃匹配")

        while True:
            sel = input("请输入序号选择 Bangumi 条目（0放弃）：").strip()
            if sel.isdigit():
                sel_int = int(sel)
                if sel_int == 0:
                    return None
                if 1 <= sel_int <= len(candidates):
                    return str(candidates[sel_int - 1][1]["id"])
            print("输入无效，请重新输入。")

    def fetch_game(self, subject_id: str) -> dict:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        r = requests.get(url, headers=self.headers)
        if r.status_code != 200:
            return {}
        d = r.json()
        # 从 images 字段优先取 large，fallback用 image
        cover_url = d.get("images", {}).get("large") or d.get("image") or ""
        return {
            "title": d.get("name"),
            "title_cn": d.get("name_cn"),
            "release_date": d.get("date"),
            "summary": d.get("summary", ""),
            "url": f"https://bangumi.tv/subject/{subject_id}",
            "封面图链接": cover_url,
        }


    def fetch_characters(self, subject_id: str) -> list:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        r = requests.get(url, headers=self.headers)
        if r.status_code != 200:
            return []

        characters = []
        for ch in r.json():
            char_id = ch["id"]
            detail_resp = requests.get(f"https://api.bgm.tv/v0/characters/{char_id}", headers=self.headers)
            if detail_resp.status_code != 200:
                continue
            detail = detail_resp.json()
            raw_stats = detail.get("infobox", [])
            stats = {}
            for item in raw_stats:
                key = item.get("key")
                val = item.get("value")
                if not key or val is None:
                    continue
                for canonical, aliases in FIELD_ALIASES.items():
                    if key in aliases:
                        if isinstance(val, list):
                            stats[canonical] = ", ".join([f"{i['k']}: {i['v']}" for i in val if isinstance(i, dict)])
                        else:
                            stats[canonical] = val
                        break

            aliases = set()
            if detail.get("name_cn"):
                aliases.add(detail["name_cn"])
            alias_raw = stats.get("character_alias")
            if isinstance(alias_raw, str):
                aliases.update([a.strip() for a in re.split(r"[、,，/／；;]", alias_raw)])
            elif isinstance(alias_raw, list):
                for item in alias_raw:
                    val = item.strip() if isinstance(item, str) else item.get("v", "").strip()
                    aliases.add(val)

            characters.append(
                {
                    "name": detail["name"],
                    "cv": ch["actors"][0]["name"] if ch.get("actors") else "",
                    "avatar": detail.get("images", {}).get("large", ""),
                    "summary": detail.get("summary", "").strip(),
                    "bwh": stats.get("character_bwh", ""),
                    "height": stats.get("character_height", ""),
                    "gender": stats.get("character_gender", ""),
                    "birthday": stats.get("character_birthday", ""),
                    "blood_type": stats.get("character_blood_type", ""),
                    "url": f"https://bangumi.tv/character/{char_id}",
                    "aliases": list(aliases),
                }
            )
        return characters

    def _character_exists(self, url: str) -> str | None:
        query_url = f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query"
        payload = {"filter": {"property": "详情页面", "url": {"equals": url}}}
        resp = self.notion._request("POST", query_url, payload)
        results = resp.get("results", []) if resp else []
        return results[0]["id"] if results else None

    def create_or_update_character(self, char: dict) -> str | None:
        existing_id = self._character_exists(char["url"])
        if existing_id:
            logging.info(f"角色已存在，跳过创建：{char['name']}")
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
        if char.get("height"):
            props[FIELDS["character_height"]] = {"rich_text": [{"text": {"content": char["height"]}}]}
        if char.get("birthday"):
            props[FIELDS["character_birthday"]] = {"rich_text": [{"text": {"content": char["birthday"]}}]}
        if char.get("blood_type"):
            props[FIELDS["character_blood_type"]] = {"select": {"name": char["blood_type"]}}
        if char.get("summary"):
            props["简介"] = {"rich_text": [{"text": {"content": char["summary"]}}]}
        if char.get("avatar"):
            props["头像"] = {
                "files": [
                    {
                        "type": "external",
                        "name": "avatar",
                        "external": {"url": char["avatar"]},
                    }
                ]
            }
        if char.get("aliases"):
            alias_text = "、".join(char["aliases"][:20])
            props["别名"] = {"rich_text": [{"text": {"content": alias_text}}]}

        payload = {"parent": {"database_id": CHARACTER_DB_ID}, "properties": props}
        r = requests.post("https://api.notion.com/v1/pages", headers=self.notion.headers, json=payload)
        return r.json().get("id") if r.status_code == 200 else None

    def create_or_link_characters(self, game_page_id: str, subject_id: str):
        characters = self.fetch_characters(subject_id)
        character_relations = []
        all_cvs = set()
        for ch in characters:
            char_id = self.create_or_update_character(ch)
            if char_id:
                character_relations.append({"id": char_id})
            if ch.get("cv"):
                all_cvs.add(ch["cv"].strip())
            time.sleep(0.3)

        patch = {
            FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"},
            FIELDS["game_characters"]: {"relation": character_relations},
        }
        if all_cvs:
            patch[FIELDS["voice_actor"]] = {"multi_select": [{"name": name} for name in sorted(all_cvs)]}
        self.notion._request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{game_page_id}",
            {"properties": patch},
        )
        logging.info("Bangumi角色信息同步完成")

    def fetch_brand_info_from_bangumi(self, brand_name: str) -> dict | None:
        def search_brand(keyword: str):
            print(f"🔍 正在搜索 Bangumi 品牌关键词: {keyword}")
            url = "https://api.bgm.tv/v0/search/persons"
            headers = {
                "Authorization": f"Bearer {BANGUMI_TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "OtakuNotionSync/1.0",
            }
            data = {
                "keyword": keyword,
                "filter": {"career": ["artist", "director", "producer"]},
            }
            resp = requests.post(url, headers=headers, json=data)
            if resp.status_code != 200:
                print(f"❌ Bangumi 搜索失败，状态码: {resp.status_code}，响应: {resp.text}")
                return []
            results = resp.json().get("data", [])
            print(f"✅ 搜索结果数: {len(results)}")
            return results

        primary_name = extract_primary_brand_name(brand_name)
        print(f"🎯 提取主品牌名: {primary_name}")

        # 只用主品牌名作为搜索关键词，避免重复搜索带括号的名字
        search_keywords = [primary_name] if primary_name else [brand_name]

        best_match, best_score = None, 0
        for keyword in search_keywords:
            results = search_brand(keyword)
            for r in results:
                candidate_name = r.get("name", "")
                infobox = r.get("infobox", [])
                aliases = extract_aliases(infobox)
                names = [candidate_name] + aliases
                score = max(difflib.SequenceMatcher(None, brand_name.lower(), n.lower()).ratio() for n in names)
                print(f"🧪 候选: {candidate_name} | 相似度: {score:.2f} | 别名: {aliases}")
                if score > best_score:
                    best_score = score
                    best_match = r
            if best_score >= 0.85:
                print(f"✅ 提前匹配成功: {best_match.get('name')} (得分: {best_score:.2f})")
                break

        if not best_match or best_score < 0.7:
            print(f"⚠️ 未找到相似度高于阈值的品牌（最高: {best_score:.2f}）")
            return None

        infobox = best_match.get("infobox", [])
        links = extract_link_map(infobox)
        summary = best_match.get("summary", "")
        icon_url = best_match.get("img")
        birthday = extract_first_valid(infobox, FIELD_ALIASES.get("brand_birthday", []))
        company_address = extract_first_valid(infobox, ["公司地址", "地址", "所在地", "所在地地址"])
        bangumi_url = f"https://bgm.tv/person/{best_match['id']}" if best_match.get("id") else None
        aliases = extract_aliases(infobox)

        twitter = links.get("brand_twitter") or links.get("Twitter") or ""
        if twitter.startswith("@"):
            twitter = f"https://twitter.com/{twitter[1:]}"

        print(f"✅ 最终匹配品牌: {best_match.get('name')} (ID: {best_match.get('id')})")

        return {
            "summary": summary,
            "icon": icon_url,
            "birthday": birthday,
            "company_address": company_address,
            "homepage": links.get("brand_official_url") or links.get("官网"),
            "twitter": twitter,
            "bangumi_url": bangumi_url,
            "alias": aliases,
        }
