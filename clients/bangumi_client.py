# clients/bangumi_client.py
# 该模块用于与 Bangumi API 交互，获取游戏和角色信息
import asyncio
import difflib
import json
import os
import re
import time
import unicodedata

import httpx

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN, CHARACTER_DB_ID
from utils import logger
from utils.field_helper import extract_aliases, extract_first_valid, extract_link_map

API_TOKEN = BANGUMI_TOKEN
HEADERS_API = {
    "Authorization": f"Bearer {API_TOKEN}",
    "User-Agent": "BangumiSync/1.0",
    "Accept": "application/json",
}

alias_path = os.path.join(os.path.dirname(__file__), "../config/field_aliases.json")
with open(alias_path, "r", encoding="utf-8") as f:
    FIELD_ALIASES = json.load(f)


# --- 辅助函数 normalize_title, extract_primary_brand_name, clean_title, simplify_title 不变 ---
def normalize_title(title: str) -> str:
    if not title:
        return ""
    title = unicodedata.normalize("NFKC", title)
    title = title.replace("～", "〜").replace("’", "'").replace("“", '"').replace("”", '"')
    title = re.sub(r"[！!]", "!", title)
    title = re.sub(r"[ー─━―‐‑‒–—―]", "-", title)
    title = re.sub(r"\s+", "", title)
    return title.lower().strip()


def extract_primary_brand_name(name: str) -> str:
    if not name:
        return name
    return re.sub(r"[（(].*?[）)]", "", name).strip()


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
    def __init__(self, notion: NotionClient, client: httpx.AsyncClient):
        self.notion = notion
        self.client = client
        self.headers = HEADERS_API
        self.similarity_threshold = 0.85

    async def _search(self, keyword: str):
        url = "https://api.bgm.tv/v0/search/subjects"
        payload = {"keyword": keyword, "sort": "rank", "filter": {"type": [4], "nsfw": True}}
        try:
            resp = await self.client.post(url, headers=self.headers, json=payload, timeout=15)
            if resp.status_code != 200:
                logger.warn(f"[Bangumi] API搜索失败: {resp.status_code}")
                return []
            return resp.json().get("data", [])
        except httpx.RequestError as e:
            logger.error(f"[Bangumi] API请求异常: {e}")
            return []

    async def search_and_select_bangumi_id(self, keyword: str) -> str | None:
        raw_results = await self._search(keyword)
        if not raw_results:
            simplified = simplify_title(keyword)
            if simplified != keyword:
                raw_results = await self._search(simplified)
            if not raw_results:
                return None

        # --- 匹配和选择逻辑不变 ---
        norm_kw = normalize_title(keyword)
        clean_kw = normalize_title(clean_title(keyword))
        simp_kw = normalize_title(simplify_title(keyword))

        candidates = []
        for item in raw_results:
            name, name_cn = item.get("name", ""), item.get("name_cn", "")
            norm_name, norm_cn = normalize_title(name), normalize_title(name_cn)
            ratios = [
                difflib.SequenceMatcher(None, norm_kw, norm_name).ratio(),
                difflib.SequenceMatcher(None, clean_kw, normalize_title(clean_title(name))).ratio(),
                difflib.SequenceMatcher(
                    None, simp_kw, normalize_title(simplify_title(name))
                ).ratio(),
                difflib.SequenceMatcher(None, norm_kw, norm_cn).ratio(),
            ]
            candidates.append((max(ratios), item))

        candidates.sort(key=lambda x: x[0], reverse=True)

        for _, item in candidates:
            item_clean = clean_title(item.get("name", ""))
            keyword_clean = clean_title(keyword)
            if item_clean and (keyword_clean in item_clean):
                logger.info(f"[Bangumi] 子串匹配成功: {item['name']}，视为同一作品")
                return str(item["id"])

        if candidates and candidates[0][0] >= self.similarity_threshold:
            best = candidates[0][1]
            logger.info(f"[Bangumi] 自动匹配成功: {best['name']} (相似度 {candidates[0][0]:.2f})")
            return str(best["id"])

        if candidates and candidates[0][0] >= 0.7:
            best = candidates[0][1]
            if clean_title(best["name"]) in clean_title(keyword) or clean_title(
                keyword
            ) in clean_title(best["name"]):
                logger.info(
                    f"[Bangumi] 模糊匹配成功（放宽判定）: {best['name']} (相似度 {candidates[0][0]:.2f})"
                )
                return str(best["id"])

        logger.warn("Bangumi自动匹配相似度不足，请手动选择:")
        for idx, (ratio, item) in enumerate(candidates[:10]):
            print(
                f"  {idx + 1}. {item['name']} / {item.get('name_cn','') or ''} (相似度: {ratio:.2f})"
            )
        print("  0. 放弃匹配")

        while True:
            sel = input("请输入序号选择 Bangumi 条目（0放弃）：").strip()
            if sel.isdigit():
                sel_int = int(sel)
                if sel_int == 0:
                    return None
                if 1 <= sel_int <= len(candidates):
                    return str(candidates[sel_int - 1][1]["id"])
            logger.error("输入无效，请重新输入。")

    async def fetch_game(self, subject_id: str) -> dict:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        r = await self.client.get(url, headers=self.headers)
        if r.status_code != 200:
            return {}
        d = r.json()
        cover_url = d.get("images", {}).get("large") or d.get("image") or ""
        return {
            "title": d.get("name"),
            "title_cn": d.get("name_cn"),
            "release_date": d.get("date"),
            "summary": d.get("summary", ""),
            "url": f"https://bangumi.tv/subject/{subject_id}",
            "封面图链接": cover_url,
        }

    async def fetch_character_detail(self, char_id: int):
        """获取单个角色详情的辅助函数"""
        detail_resp = await self.client.get(
            f"https://api.bgm.tv/v0/characters/{char_id}", headers=self.headers
        )
        if detail_resp.status_code != 200:
            return None
        return detail_resp.json()

    async def fetch_characters(self, subject_id: str) -> list:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        r = await self.client.get(url, headers=self.headers)
        if r.status_code != 200:
            return []

        char_list = r.json()
        # 并发获取所有角色的详细信息
        tasks = [self.fetch_character_detail(ch["id"]) for ch in char_list]
        details_list = await asyncio.gather(*tasks)

        characters = []
        for ch, detail in zip(char_list, details_list):
            if not detail:
                continue

            # --- 解析逻辑不变 ---
            raw_stats = detail.get("infobox", [])
            stats = {}
            for item in raw_stats:
                key, val = item.get("key"), item.get("value")
                if not key or val is None:
                    continue
                for canonical, aliases in FIELD_ALIASES.items():
                    if key in aliases:
                        if isinstance(val, list):
                            stats[canonical] = ", ".join(
                                [f"{i['k']}: {i['v']}" for i in val if isinstance(i, dict)]
                            )
                        else:
                            stats[canonical] = val
                        break

            aliases = {detail["name_cn"]} if detail.get("name_cn") else set()
            for a in extract_aliases(raw_stats, alias_type="character_alias"):
                aliases.add(a.strip())

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
                    "url": f"https://bangumi.tv/character/{ch['id']}",
                    "aliases": list(aliases),
                }
            )
        return characters

    async def _character_exists(self, url: str) -> str | None:
        payload = {"filter": {"property": "详情页面", "url": {"equals": url}}}
        resp = await self.notion._request(
            "POST", f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query", payload
        )
        return resp["results"][0]["id"] if resp and resp.get("results") else None

    async def create_or_update_character(self, char: dict) -> str | None:
        existing_id = await self._character_exists(char["url"])
        props = {
            "角色名称": {"title": [{"text": {"content": char["name"]}}]},
            "详情页面": {"url": char["url"]},
        }
        # --- property building logic is unchanged ---
        if char.get("cv"):
            props["声优"] = {"rich_text": [{"text": {"content": char["cv"]}}]}
        if char.get("gender"):
            props["性别"] = {"select": {"name": char["gender"]}}
        if char.get("bwh"):
            props["BWH"] = {"rich_text": [{"text": {"content": char["bwh"]}}]}
        if char.get("height"):
            props[FIELDS["character_height"]] = {
                "rich_text": [{"text": {"content": char["height"]}}]
            }
        if char.get("birthday"):
            props[FIELDS["character_birthday"]] = {
                "rich_text": [{"text": {"content": char["birthday"]}}]
            }
        if char.get("blood_type"):
            props[FIELDS["character_blood_type"]] = {"select": {"name": char["blood_type"]}}
        if char.get("summary"):
            props["简介"] = {"rich_text": [{"text": {"content": char["summary"]}}]}
        if char.get("avatar"):
            props["头像"] = {
                "files": [
                    {"type": "external", "name": "avatar", "external": {"url": char["avatar"]}}
                ]
            }
        if char.get("aliases"):
            alias_text = "、".join(char["aliases"][:20])
            props["别名"] = {"rich_text": [{"text": {"content": alias_text}}]}

        if existing_id:
            resp = await self.notion._request(
                "PATCH", f"https://api.notion.com/v1/pages/{existing_id}", {"properties": props}
            )
            if resp:
                logger.info(f"角色已存在，已更新：{char['name']}")
            return existing_id if resp else None
        else:
            payload = {"parent": {"database_id": CHARACTER_DB_ID}, "properties": props}
            resp = await self.notion._request("POST", "https://api.notion.com/v1/pages", payload)
            if resp:
                logger.success(f"新角色已创建：{char['name']}")
            return resp.get("id") if resp else None

    async def create_or_link_characters(self, game_page_id: str, subject_id: str):
        characters = await self.fetch_characters(subject_id)

        # 并发创建或更新角色
        tasks = [self.create_or_update_character(ch) for ch in characters]
        char_ids = await asyncio.gather(*tasks)

        character_relations = [{"id": cid} for cid in char_ids if cid]
        all_cvs = {ch["cv"].strip() for ch in characters if ch.get("cv")}

        patch = {
            FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"},
            FIELDS["game_characters"]: {"relation": character_relations},
        }
        if all_cvs:
            patch[FIELDS["voice_actor"]] = {
                "multi_select": [{"name": name} for name in sorted(all_cvs)]
            }
        await self.notion._request(
            "PATCH", f"https://api.notion.com/v1/pages/{game_page_id}", {"properties": patch}
        )
        logger.success("Bangumi角色信息同步完成")

    async def fetch_brand_info_from_bangumi(self, brand_name: str) -> dict | None:
        async def search_brand(keyword: str):
            logger.info(f"[Bangumi] 正在搜索品牌关键词: {keyword}")
            url = "https://api.bgm.tv/v0/search/persons"
            data = {"keyword": keyword, "filter": {"career": ["artist", "director", "producer"]}}
            resp = await self.client.post(url, headers=self.headers, json=data)
            if resp.status_code != 200:
                logger.error(f"[Bangumi] 品牌搜索失败，状态码: {resp.status_code}")
                return []
            results = resp.json().get("data", [])
            logger.info(f"搜索到 {len(results)} 个结果")
            return results

        primary_name = extract_primary_brand_name(brand_name)

        # --- 匹配和解析逻辑不变 ---
        best_match, best_score = None, 0
        results = await search_brand(primary_name or brand_name)
        for r in results:
            candidate_name = r.get("name", "")
            infobox = r.get("infobox", [])
            aliases = extract_aliases(infobox, alias_type="brand_alias")
            names = [candidate_name] + aliases
            score = max(
                difflib.SequenceMatcher(None, brand_name.lower(), n.lower()).ratio() for n in names
            )
            if score > best_score:
                best_score, best_match = score, r

        if not best_match or best_score < 0.7:
            logger.warn(f"未找到相似度高于阈值的品牌（最高: {best_score:.2f}）")
            return None

        logger.success(
            f"[Bangumi] 最终匹配品牌: {best_match.get('name')} (ID: {best_match.get('id')}, 相似度: {best_score:.2f})"
        )
        infobox = best_match.get("infobox", [])
        links = extract_link_map(infobox)
        twitter = links.get("brand_twitter") or links.get("Twitter") or ""
        if twitter.startswith("@"):
            twitter = f"https://twitter.com/{twitter[1:]}"

        return {
            "summary": best_match.get("summary", ""),
            "icon": best_match.get("img"),
            "birthday": extract_first_valid(infobox, FIELD_ALIASES.get("brand_birthday", [])),
            "company_address": extract_first_valid(infobox, ["公司地址", "地址", "所在地"]),
            "homepage": links.get("brand_official_url") or links.get("官网"),
            "twitter": twitter,
            "bangumi_url": (
                f"https://bgm.tv/person/{best_match['id']}" if best_match.get("id") else None
            ),
            "alias": extract_aliases(infobox, alias_type="brand_alias"),
        }
