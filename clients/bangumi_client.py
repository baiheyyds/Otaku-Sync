# clients/bangumi_client.py
# 该模块用于与 Bangumi API 交互，获取游戏和角色信息
import asyncio
import difflib
import json
import os
import re
import time
import unicodedata
from typing import Set

import httpx

from clients.notion_client import NotionClient
from config.config_fields import FIELDS
from config.config_token import BANGUMI_TOKEN, BRAND_DB_ID, CHARACTER_DB_ID
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager
from utils import logger

API_TOKEN = BANGUMI_TOKEN
HEADERS_API = {
    "Authorization": f"Bearer {API_TOKEN}",
    "User-Agent": "BangumiSync/1.0",
    "Accept": "application/json",
}


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
    def __init__(
        self,
        notion: NotionClient,
        mapper: BangumiMappingManager,
        schema: NotionSchemaManager,
        client: httpx.AsyncClient,
    ):
        self.notion = notion
        self.mapper = mapper
        self.schema = schema
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

        # 【新增】处理 infobox，使其具备学习能力
        # 注意：目标数据库是 GAME_DB_ID
        infobox_data = await self._process_infobox(d.get("infobox", []), self.notion.game_db_id)

        cover_url = d.get("images", {}).get("large") or d.get("image") or ""

        # 基础信息
        game_data = {
            "title": d.get("name"),
            "title_cn": d.get("name_cn"),
            "release_date": d.get("date"),
            "summary": d.get("summary", ""),
            "url": f"https://bangumi.tv/subject/{subject_id}",
            "封面图链接": cover_url,
        }

        # 【新增】将从 infobox 学到的属性合并进来
        game_data.update(infobox_data)

        return game_data

    async def _process_infobox(self, infobox: list, target_db_id: str) -> dict:
        processed = {}
        if not infobox:
            return processed

        for item in infobox:
            bangumi_key, bangumi_value = item.get("key"), item.get("value")
            if not bangumi_key or not bangumi_value:
                continue

            # --- 核心改动：新增对 [{k:v}, ...] 结构的特殊处理 ---
            is_key_value_list = (
                isinstance(bangumi_value, list)
                and bangumi_value
                and isinstance(bangumi_value[0], dict)
                and "k" in bangumi_value[0]
                and "v" in bangumi_value[0]
            )

            if is_key_value_list:
                # 遍历列表中的每一个键值对对象
                for sub_item in bangumi_value:
                    # 将内部的 k 作为新的 bangumi_key
                    sub_key = sub_item.get("k")
                    sub_value = sub_item.get("v")
                    if not sub_key or not sub_value:
                        continue

                    # 使用这个新的 sub_key 进行映射查询或学习
                    notion_prop = self.mapper.get_notion_prop(sub_key)
                    if not notion_prop:
                        notion_prop = await self.mapper.handle_new_key(
                            sub_key, self.notion, self.schema, target_db_id
                        )

                    if notion_prop:
                        processed[notion_prop] = str(sub_value).strip()

                # 处理完这种特殊结构后，跳到下一个 infobox 项目
                continue
            # --- 核心改动结束 ---

            # --- 以下是处理常规infobox项目的现有逻辑 ---

            # 处理常规列表，如 [{"v": "value1"}, {"v": "value2"}]
            if isinstance(bangumi_value, list):
                value_str = ", ".join(
                    [v.get("v", v) if isinstance(v, dict) else str(v) for v in bangumi_value]
                )
            # 处理简单字符串
            else:
                value_str = str(bangumi_value)

            # 使用原始的 bangumi_key 进行映射
            notion_prop = self.mapper.get_notion_prop(bangumi_key)
            if not notion_prop:
                notion_prop = await self.mapper.handle_new_key(
                    bangumi_key, self.notion, self.schema, target_db_id
                )

            if notion_prop:
                processed[notion_prop] = value_str.strip()

        return processed

    async def fetch_characters(self, subject_id: str) -> list:
        # 第一步：获取包含声优(actors)的角色列表
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        r = await self.client.get(url, headers=self.headers)
        if r.status_code != 200:
            return []

        # char_list_with_actors 中包含了角色ID和直接关联的声优信息
        char_list_with_actors = r.json()
        if not char_list_with_actors:
            return []

        # 第二步：并发获取每个角色的详细信息（用于infobox等补充数据）
        tasks = [
            self.client.get(f"https://api.bgm.tv/v0/characters/{ch['id']}", headers=self.headers)
            for ch in char_list_with_actors
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        characters = []
        # 同时遍历初始列表和详细信息响应
        for char_summary, detail_resp in zip(char_list_with_actors, responses):
            # 跳过获取失败的角色详情
            if isinstance(detail_resp, Exception) or detail_resp.status_code != 200:
                continue

            detail = detail_resp.json()

            # --- 核心修复：在这里整合数据 ---

            # 1. 从角色详情的 infobox 获取数据 (生日, BWH, etc.)
            infobox_data = await self._process_infobox(detail.get("infobox", []), CHARACTER_DB_ID)

            # 2. 从初始列表的 `actors` 字段直接获取声优信息 (如果存在)
            voice_actor = None
            if char_summary.get("actors"):
                voice_actor = char_summary["actors"][0].get("name")

            # 3. 构建最终的角色数据字典
            aliases = {detail.get("name_cn")} if detail.get("name_cn") else set()
            if "别名" in infobox_data:
                # 兼容字符串和列表形式的别名
                alias_value = infobox_data["别名"]
                if isinstance(alias_value, str):
                    aliases.update([a.strip() for a in alias_value.split(",")])
                elif isinstance(alias_value, list):
                    aliases.update([a.strip() for a in alias_value])

            character_data = {
                "name": detail["name"],
                "avatar": detail.get("images", {}).get("large", ""),
                "summary": detail.get("summary", "").strip(),
                "url": f"https://bangumi.tv/character/{detail['id']}",
                "aliases": list(filter(None, aliases)),
            }

            # 如果从 actors 字段获取到了声优，就添加到数据中
            if voice_actor:
                character_data["声优"] = voice_actor

            # 将 infobox 中的其他数据（如生日、性别等）合并进来
            character_data.update(infobox_data)

            characters.append(character_data)
            # --- 修复结束 ---

        return characters

    async def _character_exists(self, url: str) -> str | None:
        payload = {"filter": {"property": FIELDS["character_url"], "url": {"equals": url}}}
        resp = await self.notion._request(
            "POST", f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query", payload
        )
        return resp["results"][0]["id"] if resp and resp.get("results") else None

    async def create_or_update_character(self, char: dict, warned_keys: Set[str]) -> str | None:
        existing_id = await self._character_exists(char["url"])

        # --- 核心修复：构建一个更全面的映射表 ---
        # 这个映射表能处理所有在 config 中定义过的角色字段
        # key 是从 Bangumi 传来的内部键 (如 'name', '声优'), value 是 Notion 属性名
        key_to_notion_map = {
            "name": FIELDS["character_name"],
            "aliases": FIELDS["character_alias"],
            "avatar": FIELDS["character_avatar"],
            "summary": FIELDS["character_summary"],
            "url": FIELDS["character_url"],
            "声优": FIELDS["character_cv"],  # 明确添加声优映射
            "生日": FIELDS["character_birthday"],
            "血型": FIELDS["character_blood_type"],
            "性别": FIELDS["character_gender"],
            "BWH": FIELDS["character_bwh"],
            "身高": FIELDS["character_height"],
        }
        # --- 修复结束 ---

        props = {}
        for internal_key, value in char.items():
            if not value:
                continue

            # 优先使用映射表，如果找不到，则直接使用 key 本身 (用于未来可能的新增字段)
            notion_prop_name = key_to_notion_map.get(internal_key, internal_key)
            prop_type = self.schema.get_property_type(CHARACTER_DB_ID, notion_prop_name)

            if not prop_type:
                if notion_prop_name not in warned_keys:
                    logger.warn(f"角色属性 '{notion_prop_name}' 在 Notion 角色库中不存在，已跳过。")
                    warned_keys.add(notion_prop_name)
                continue

            # 为角色页面构建属性 (确保 select 和 rich_text 被正确处理)
            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}
            elif prop_type == "rich_text":
                # 将列表形式的别名等转换为顿号分隔的字符串
                content = "、".join(value) if isinstance(value, list) else str(value)
                props[notion_prop_name] = {"rich_text": [{"text": {"content": content}}]}
            elif prop_type == "url":
                props[notion_prop_name] = {"url": str(value)}
            elif prop_type == "files":
                props[notion_prop_name] = {
                    "files": [{"type": "external", "name": "avatar", "external": {"url": value}}]
                }
            elif prop_type == "select":
                if str(value).strip():
                    props[notion_prop_name] = {"select": {"name": str(value)}}

        # 确保关键字段存在
        if FIELDS["character_name"] not in props:
            props[FIELDS["character_name"]] = {"title": [{"text": {"content": char["name"]}}]}
        if FIELDS["character_url"] not in props:
            props[FIELDS["character_url"]] = {"url": char["url"]}

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
        # 1. 正常获取所有角色的详细信息
        characters = await self.fetch_characters(subject_id)
        if not characters:
            logger.info("未找到任何 Bangumi 角色信息，跳过角色关联。")
            # 即使没有角色，也要确保 Bangumi URL 被写入
            patch = {
                "properties": {
                    FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"}
                }
            }
            await self.notion._request(
                "PATCH", f"https://api.notion.com/v1/pages/{game_page_id}", patch
            )
            return

        # 2. 调用已修复的 `create_or_update_character`，确保每个角色页面信息完整
        warned_keys_for_this_game = set()
        tasks = [
            self.create_or_update_character(ch, warned_keys_for_this_game) for ch in characters
        ]
        char_ids = await asyncio.gather(*tasks)
        character_relations = [{"id": cid} for cid in char_ids if cid]

        # 3. 智能更新【游戏页面】
        page_data = await self.notion.get_page(game_page_id)
        if not page_data:
            logger.error(f"无法获取游戏页面 {game_page_id} 的当前状态，跳过声优补充。")
            return

        patch_props = {
            FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"},
            FIELDS["game_characters"]: {"relation": character_relations},
        }

        # 检查游戏页面的声优字段
        existing_vcs = (
            page_data.get("properties", {}).get(FIELDS["voice_actor"], {}).get("multi_select", [])
        )

        if not existing_vcs:
            logger.info("游戏页面声优信息为空，尝试从 Bangumi 角色数据中补充...")
            all_cvs = {ch["声优"].strip() for ch in characters if ch.get("声优")}
            if all_cvs:
                logger.success(f"已为【游戏页面】补充 {len(all_cvs)} 位声优。")
                patch_props[FIELDS["voice_actor"]] = {
                    "multi_select": [{"name": name} for name in sorted(all_cvs)]
                }
            else:
                logger.info("Bangumi 角色数据中也未找到声优信息以供补充。")
        else:
            logger.info("游戏页面已存在声优信息，跳过补充。")

        # 4. 执行最终的 PATCH 请求
        await self.notion._request(
            "PATCH", f"https://api.notion.com/v1/pages/{game_page_id}", {"properties": patch_props}
        )
        logger.success("Bangumi 角色信息同步与关联完成。")

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
        best_match, best_score = None, 0
        results = await search_brand(primary_name or brand_name)
        for r in results:
            candidate_name = r.get("name", "")
            infobox = r.get("infobox", [])

            aliases = []
            aliases_value = next(
                (
                    item.get("value")
                    for item in infobox
                    if self.mapper.get_notion_prop(item.get("key")) == "别名"
                ),
                None,
            )
            if isinstance(aliases_value, str):
                aliases = [a.strip() for a in aliases_value.split(",")]
            elif isinstance(aliases_value, list):
                aliases = [str(v.get("v", v)) for v in aliases_value if v]

            names = [candidate_name] + aliases
            valid_names = [n for n in names if n and isinstance(n, str)]
            if not valid_names:
                continue
            score = max(
                difflib.SequenceMatcher(None, brand_name.lower(), n.lower()).ratio()
                for n in valid_names
            )
            if score > best_score:
                best_score, best_match = score, r

        if not best_match or best_score < 0.7:
            logger.warn(f"未找到相似度高于阈值的品牌（最高: {best_score:.2f}）")
            return None

        logger.success(
            f"[Bangumi] 最终匹配品牌: {best_match.get('name')} (ID: {best_match.get('id')}, 相似度: {best_score:.2f})"
        )

        infobox_data = await self._process_infobox(best_match.get("infobox", []), BRAND_DB_ID)

        brand_info = {
            "summary": best_match.get("summary", ""),
            "icon": best_match.get("img"),
            "bangumi_url": (
                f"https://bgm.tv/person/{best_match['id']}" if best_match.get("id") else None
            ),
        }
        brand_info.update(infobox_data)

        if "官网" in brand_info:
            brand_info["homepage"] = brand_info.pop("官网")
        if (
            "Twitter" in brand_info
            and isinstance(brand_info["Twitter"], str)
            and brand_info["Twitter"].startswith("@")
        ):
            brand_info["twitter"] = f"https://twitter.com/{brand_info['Twitter'][1:]}"
        else:
            brand_info["twitter"] = brand_info.get("Twitter")

        return brand_info
