# clients/bangumi_client.py
# 该模块用于与 Bangumi API 交互，获取游戏和角色信息
import asyncio
import logging
from rapidfuzz import fuzz

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
from core.interaction import InteractionProvider
from core.mapping_manager import BangumiMappingManager
from core.schema_manager import NotionSchemaManager

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
        interaction_provider: InteractionProvider,
    ):
        self.notion = notion
        self.mapper = mapper
        self.schema = schema
        self.client = client
        self.interaction_provider = interaction_provider
        self.headers = HEADERS_API
        self.similarity_threshold = 0.85

    async def _search(self, keyword: str):
        url = "https://api.bgm.tv/v0/search/subjects"
        payload = {"keyword": keyword, "sort": "rank", "filter": {"type": [4], "nsfw": True}}
        try:
            resp = await self.client.post(url, headers=self.headers, json=payload, timeout=15)
            if resp.status_code != 200:
                logging.warning(f"⚠️ [Bangumi] API搜索失败: {resp.status_code}")
                return []
            return resp.json().get("data", [])
        except httpx.RequestError as e:
            logging.error(f"❌ [Bangumi] API请求异常: {e}")
            return []

    async def search_and_select_bangumi_id(self, keyword: str) -> str | None:
        raw_results = await self._search(keyword)
        if not raw_results:
            simplified = simplify_title(keyword)
            if simplified != keyword:
                raw_results = await self._search(simplified)
            if not raw_results:
                return None
        norm_kw, clean_kw, simp_kw = (
            normalize_title(keyword),
            normalize_title(clean_title(keyword)),
            normalize_title(simplify_title(keyword)),
        )
        candidates = []
        for item in raw_results:
            name, name_cn = item.get("name", ""), item.get("name_cn", "")
            norm_name, norm_cn = normalize_title(name), normalize_title(name_cn)
            ratios = [
                fuzz.ratio(norm_kw, norm_name) / 100.0,
                fuzz.ratio(clean_kw, normalize_title(clean_title(name))) / 100.0,
                fuzz.ratio(simp_kw, normalize_title(simplify_title(name))) / 100.0,
                fuzz.ratio(norm_kw, norm_cn) / 100.0,
            ]
            candidates.append((max(ratios), item))
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, item in candidates:
            if clean_title(item.get("name", "")) and (
                clean_title(keyword) in clean_title(item.get("name", ""))
            ):
                logging.info(f"🔍 [Bangumi] 子串匹配成功: {item['name']}，视为同一作品")
                return str(item["id"])
        if candidates and candidates[0][0] >= self.similarity_threshold:
            best = candidates[0][1]
            logging.info(f"🔍 [Bangumi] 自动匹配成功: {best['name']} (相似度 {candidates[0][0]:.2f})")
            return str(best["id"])
        if candidates and candidates[0][0] >= 0.7:
            best = candidates[0][1]
            if clean_title(best["name"]) in clean_title(keyword) or clean_title(
                keyword
            ) in clean_title(best["name"]):
                logging.info(
                    f"🔍 [Bangumi] 模糊匹配成功（放宽判定）: {best['name']} (相似度 {candidates[0][0]:.2f})"
                )
                return str(best["id"])
        
        logging.warning("⚠️ Bangumi自动匹配相似度不足，请手动选择:")
        
        # Format candidates for display in GUI
        gui_candidates = []
        for idx, (ratio, item) in enumerate(candidates[:10]):
            display_text = f"{idx + 1}. {item['name']} / {item.get('name_cn','') or ''} (相似度: {ratio:.2f})"
            gui_candidates.append({'id': str(item['id']), 'display': display_text})

        # Use the interaction provider to get the user's choice
        selected_id = await self.interaction_provider.get_bangumi_game_choice(keyword, gui_candidates)
        
        return selected_id

    async def fetch_game(self, subject_id: str) -> dict:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        r = await self.client.get(url, headers=self.headers)
        if r.status_code != 200:
            return {}
        d = r.json()
        bangumi_url = f"https://bangumi.tv/subject/{subject_id}"
        infobox_data = await self._process_infobox(
            d.get("infobox", []), self.notion.game_db_id, bangumi_url
        )
        cover_url = d.get("images", {}).get("large") or d.get("image") or ""
        game_data = {
            "title": d.get("name"),
            "title_cn": d.get("name_cn"),
            "release_date": d.get("date"),
            "summary": d.get("summary", ""),
            "url": f"https://bangumi.tv/subject/{subject_id}",
            "封面图链接": cover_url,
        }
        game_data.update(infobox_data)
        return game_data

    async def _process_infobox(self, infobox: list, target_db_id: str, bangumi_url: str) -> dict:
        processed = {}
        if not infobox:
            return processed

        async def _map_and_set_prop(key, value):
            if self.mapper.is_ignored(key):
                return
            if not key or not value:
                return

            notion_prop = self.mapper.get_notion_prop(key, target_db_id)
            if not notion_prop:
                notion_prop = await self.mapper.handle_new_key(
                    key, value, bangumi_url, self.notion, self.schema, target_db_id
                )

            if notion_prop:
                if notion_prop in processed:
                    current_value = processed[notion_prop]
                    if isinstance(current_value, list):
                        if isinstance(value, list):
                            current_value.extend(value)
                        else:
                            current_value.append(value)
                    else:
                        processed[notion_prop] = [current_value]
                        if isinstance(value, list):
                            processed[notion_prop].extend(value)
                        else:
                            processed[notion_prop].append(value)
                else:
                    processed[notion_prop] = value

        for item in infobox:
            bangumi_key, bangumi_value = item.get("key"), item.get("value")
            if not bangumi_key or bangumi_value is None:
                continue

            if isinstance(bangumi_value, list):
                is_structured_list = (
                    bangumi_value and isinstance(bangumi_value[0], dict) and "k" in bangumi_value[0]
                )

                if is_structured_list:
                    for sub_item in bangumi_value:
                        if isinstance(sub_item, dict):
                            sub_key = sub_item.get("k")
                            sub_value = sub_item.get("v")
                            if sub_key is not None and sub_value is not None:
                                # [最终修复]
                                # 对于 "链接" 这种key，我们直接使用其子键 (HP, Twitter) 作为映射键
                                if bangumi_key == "链接":
                                    await _map_and_set_prop(sub_key, str(sub_value).strip())
                                # 对于 "别名" 等其他结构，我们组合父子键，但传递纯净的字符串值
                                else:
                                    combined_key = f"{bangumi_key}-{sub_key}"
                                    clean_value = str(sub_value).strip()
                                    await _map_and_set_prop(combined_key, clean_value)
                else:
                    # 处理简单的值列表 (e.g., value: [{"v": "value1"}, {"v": "value2"}])
                    v_only_values = []
                    for sub_item in bangumi_value:
                        value_to_add = None
                        if isinstance(sub_item, dict) and "v" in sub_item:
                            value_to_add = sub_item.get("v")
                        elif isinstance(sub_item, str):
                            value_to_add = sub_item
                        if value_to_add is not None:
                            v_only_values.append(str(value_to_add).strip())
                    if v_only_values:
                        await _map_and_set_prop(bangumi_key, v_only_values)
            else:
                # 处理简单的键值对 (e.g., value: "some_string")
                await _map_and_set_prop(bangumi_key, str(bangumi_value).strip())

        return processed

    async def fetch_characters(self, subject_id: str) -> list:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        r = await self.client.get(url, headers=self.headers)
        if r.status_code != 200:
            return []
        char_list_with_actors = r.json()
        if not char_list_with_actors:
            return []

        tasks = [
            self.client.get(f"https://api.bgm.tv/v0/characters/{ch['id']}", headers=self.headers)
            for ch in char_list_with_actors
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        characters = []
        for char_summary, detail_resp in zip(char_list_with_actors, responses):
            if isinstance(detail_resp, Exception) or detail_resp.status_code != 200:
                continue

            detail = detail_resp.json()
            char_url = f"https://bangumi.tv/character/{detail['id']}"

            # 1. [关键修复] 完全依赖 _process_infobox 的处理结果
            infobox_data = await self._process_infobox(
                detail.get("infobox", []), CHARACTER_DB_ID, char_url
            )

            voice_actor = (
                char_summary["actors"][0].get("name") if char_summary.get("actors") else None
            )

            # 2. [关键修复] 从 infobox_data 中获取别名，不再手动拼接
            aliases = infobox_data.pop("别名", [])  # 使用 pop 获取别名，并从字典中移除，避免重复
            if isinstance(aliases, str):  # 确保别名是列表
                aliases = [a.strip() for a in aliases.split(",")]

            name_cn = detail.get("name_cn")
            if name_cn and name_cn not in aliases:
                aliases.append(name_cn)

            character_data = {
                "name": detail["name"],
                "avatar": detail.get("images", {}).get("large", ""),
                "summary": detail.get("summary", "").strip(),
                "url": char_url,
                "aliases": list(filter(None, aliases)),
            }
            if voice_actor:
                character_data["声优"] = voice_actor

            # 3. [关键修复] 合并处理好的 infobox 数据
            character_data.update(infobox_data)
            characters.append(character_data)

        return characters

    async def _character_exists(self, url: str) -> str | None:
        payload = {"filter": {"property": FIELDS["character_url"], "url": {"equals": url}}}
        resp = await self.notion._request(
            "POST", f"https://api.notion.com/v1/databases/{CHARACTER_DB_ID}/query", payload
        )
        return resp["results"][0]["id"] if resp and resp.get("results") else None

    async def create_or_update_character(self, char: dict, warned_keys: Set[str]) -> str | None:
        existing_id = await self._character_exists(char["url"])
        key_to_notion_map = {
            "name": FIELDS["character_name"],
            "aliases": FIELDS["character_alias"],
            "avatar": FIELDS["character_avatar"],
            "summary": FIELDS["character_summary"],
            "url": FIELDS["character_url"],
            "声优": FIELDS["character_cv"],
            "生日": FIELDS["character_birthday"],
            "血型": FIELDS["character_blood_type"],
            "性别": FIELDS["character_gender"],
            "BWH": FIELDS["character_bwh"],
            "身高": FIELDS["character_height"],
        }
        props = {}
        for internal_key, value in char.items():
            if not value:
                continue
            notion_prop_name = key_to_notion_map.get(internal_key, internal_key)
            prop_type = self.schema.get_property_type(CHARACTER_DB_ID, notion_prop_name)
            if not prop_type:
                if notion_prop_name not in warned_keys:
                    logging.warning(f"⚠️ 角色属性 '{notion_prop_name}' 在 Notion 角色库中不存在，已跳过。")
                    warned_keys.add(notion_prop_name)
                continue
            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}
            elif prop_type == "rich_text":
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
        if FIELDS["character_name"] not in props:
            props[FIELDS["character_name"]] = {"title": [{"text": {"content": char["name"]}}]}
        if FIELDS["character_url"] not in props:
            props[FIELDS["character_url"]] = {"url": char["url"]}
        if existing_id:
            resp = await self.notion._request(
                "PATCH", f"https://api.notion.com/v1/pages/{existing_id}", {"properties": props}
            )
            if resp:
                logging.info(f"🔍 角色已存在，已更新：{char['name']}")
            return existing_id if resp else None
        else:
            payload = {"parent": {"database_id": CHARACTER_DB_ID}, "properties": props}
            resp = await self.notion._request("POST", "https://api.notion.com/v1/pages", payload)
            if resp:
                logging.info(f"✅ 新角色已创建：{char['name']}")
            return resp.get("id") if resp else None

    async def create_or_link_characters(self, game_page_id: str, subject_id: str):
        characters = await self.fetch_characters(subject_id)
        if not characters:
            logging.info("🔍 未找到任何 Bangumi 角色信息，跳过角色关联。")
            patch = {
                "properties": {
                    FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"}
                }
            }
            await self.notion._request(
                "PATCH", f"https://api.notion.com/v1/pages/{game_page_id}", patch
            )
            return
        warned_keys_for_this_game = set()
        tasks = [
            self.create_or_update_character(ch, warned_keys_for_this_game) for ch in characters
        ]
        char_ids = await asyncio.gather(*tasks)
        character_relations = [{"id": cid} for cid in char_ids if cid]
        page_data = await self.notion.get_page(game_page_id)
        if not page_data:
            logging.error(f"❌ 无法获取游戏页面 {game_page_id} 的当前状态，跳过声优补充。")
            return
        patch_props = {
            FIELDS["bangumi_url"]: {"url": f"https://bangumi.tv/subject/{subject_id}"},
            FIELDS["game_characters"]: {"relation": character_relations},
        }
        existing_vcs = (
            page_data.get("properties", {}).get(FIELDS["voice_actor"], {}).get("multi_select", [])
        )
        if not existing_vcs:
            logging.info("🔍 游戏页面声优信息为空，尝试从 Bangumi 角色数据中补充...")
            all_cvs = {ch["声优"].strip() for ch in characters if ch.get("声优")}
            if all_cvs:
                logging.info(f"✅ 已为【游戏页面】补充 {len(all_cvs)} 位声优。")
                patch_props[FIELDS["voice_actor"]] = {
                    "multi_select": [{"name": name} for name in sorted(all_cvs)]
                }
            else:
                logging.info("🔍 Bangumi 角色数据中也未找到声优信息以供补充。")
        else:
            logging.info("🔍 游戏页面已存在声优信息，跳过补充。")
        await self.notion._request(
            "PATCH", f"https://api.notion.com/v1/pages/{game_page_id}", {"properties": patch_props}
        )
        logging.info("✅ Bangumi 角色信息同步与关联完成。")

    async def fetch_brand_info_from_bangumi(self, brand_name: str) -> dict | None:
        """[已重构] 搜索品牌，找到ID后调用 fetch_person_by_id 获取完整信息。"""

        async def search_brand(keyword: str):
            logging.info(f"🔍 [Bangumi] 正在搜索品牌关键词: {keyword}")
            url = "https://api.bgm.tv/v0/search/persons"
            data = {"keyword": keyword, "filter": {"career": ["artist", "director", "producer"]}}
            resp = await self.client.post(url, headers=self.headers, json=data)
            if resp.status_code != 200:
                logging.error(f"❌ [Bangumi] 品牌搜索失败，状态码: {resp.status_code}")
                return []
            return resp.json().get("data", [])

        primary_name = extract_primary_brand_name(brand_name)
        results = await search_brand(primary_name or brand_name)
        if not results:
            return None

        candidates = []
        for r in results:
            names = [r.get("name", "")]
            # 尝试从infobox中提取别名以提高匹配准确率
            for item in r.get("infobox", []):
                if item.get("key") == "别名" and isinstance(item.get("value"), list):
                    names.extend(
                        [v["v"] for v in item["value"] if isinstance(v, dict) and "v" in v]
                    )

            valid_names = [n for n in names if n and isinstance(n, str)]
            if not valid_names:
                continue
            score = max(
                fuzz.ratio(brand_name.lower(), n.lower()) / 100.0
                for n in valid_names
            )
            candidates.append((score, r))

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_match = candidates[0] if candidates else (0, None)

        if not best_match or best_score < 0.7:
            logging.warning(f"⚠️ 未找到相似度高于阈值的品牌（最高: {best_score:.2f})")
            return None

        person_id = best_match.get("id")
        if not person_id:
            logging.warning("⚠️ 最佳匹配项缺少ID，无法获取详细信息。")
            return None

        logging.info(
            f"✅ [Bangumi] 搜索匹配成功: {best_match.get('name')} (ID: {person_id}, 相似度: {best_score:.2f})"
        )
        return await self.fetch_person_by_id(str(person_id))

    async def fetch_person_by_id(self, person_id: str) -> dict | None:
        """[已重构] 通过 Person ID 直接获取并处理厂商/个人信息，作为唯一的数据处理源。"""
        url = f"https://api.bgm.tv/v0/persons/{person_id}"
        logging.info(f"🔍 [Bangumi] 正在通过 ID 直接获取品牌信息: {person_id}")
        try:
            resp = await self.client.get(url, headers=self.headers)
            if resp.status_code != 200:
                logging.error(
                    f"❌ [Bangumi] 品牌信息获取失败，ID: {person_id}, 状态码: {resp.status_code}"
                )
                return None

            person_data = resp.json()
            person_url = f"https://bgm.tv/person/{person_id}"

            # 1. 完全依赖 _process_infobox 来处理所有动态字段
            infobox_data = await self._process_infobox(
                person_data.get("infobox", []), BRAND_DB_ID, person_url
            )

            # 2. 组装最终结果
            brand_info = {
                "summary": person_data.get("summary", ""),
                "icon": person_data.get("images", {}).get("large"),
                "bangumi_url": person_url,
            }
            brand_info.update(infobox_data)

            logging.info(f"✅ [Bangumi] 已成功获取并处理品牌: {person_data.get('name')}")
            return brand_info

        except Exception as e:
            logging.error(f"❌ [Bangumi] 通过ID获取品牌信息时发生异常: {e}")
            return None

    async def fetch_and_prepare_character_data(self, character_id: str) -> dict | None:
        """获取并处理单个角色的所有 Bangumi 数据，返回一个可直接用于更新的字典。"""
        try:
            char_detail_url = f"https://api.bgm.tv/v0/characters/{character_id}"
            resp = await self.client.get(char_detail_url, headers=self.headers)
            if resp.status_code != 200:
                logging.error(f"❌ 获取角色 {character_id} 详情失败: 状态码 {resp.status_code}")
                return None

            detail = resp.json()
            char_url = f"https://bangumi.tv/character/{detail['id']}"

            # 复用强大的 _process_infobox 逻辑
            infobox_data = await self._process_infobox(
                detail.get("infobox", []), CHARACTER_DB_ID, char_url
            )

            # 准备一个干净的数据字典
            char_data_to_update = {
                "name": detail.get("name"),
                "aliases": [detail.get("name_cn")] if detail.get("name_cn") else [],
                "avatar": detail.get("images", {}).get("large", ""),
                "summary": detail.get("summary", "").strip(),
                "url": char_url,
            }
            # 合并 infobox 处理结果
            char_data_to_update.update(infobox_data)

            return char_data_to_update
        except Exception as e:
            logging.error(f"❌ 处理角色 {character_id} 数据时出错: {e}")
            return None
