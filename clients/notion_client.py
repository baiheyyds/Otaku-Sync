# clients/notion_client.py
# 该模块用于与 Notion API 交互，处理游戏和品牌数据的
import asyncio
import re
import time
from datetime import datetime

import httpx

from config.config_fields import FIELDS
from utils import logger
from utils.utils import convert_date_jp_to_iso


class NotionClient:
    def __init__(self, token, game_db_id, brand_db_id, client: httpx.AsyncClient):
        self.token = token
        self.game_db_id = game_db_id
        self.brand_db_id = brand_db_id
        self.client = client
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    async def _raw_request(self, method, url, json_data=None):
        try:
            if method.upper() == "POST":
                r = await self.client.post(url, headers=self.headers, json=json_data)
            elif method.upper() == "PATCH":
                r = await self.client.patch(url, headers=self.headers, json=json_data)
            elif method.upper() == "GET":
                r = await self.client.get(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if hasattr(e, "response") and e.response:
                logger.error(f"Notion API 请求失败: {e}. 响应: {e.response.text}")
            else:
                logger.error(f"Notion API 请求失败: {e}")
            return None

    async def _request(self, method, url, json_data=None, retries=3, delay=2):
        for attempt in range(retries):
            resp = await self._raw_request(method, url, json_data)
            if resp is not None:
                return resp
            if attempt < retries - 1:
                logger.warn(f"🔁 重试 Notion API ({attempt + 1}/{retries})...")
                await asyncio.sleep(delay)
        logger.error("⛔ 最终重试失败，跳过该请求")
        return None

    def get_page_title(self, page):
        try:
            if "properties" not in page:
                logger.error(f"DEBUG get_page_title page missing properties: {page.keys()}")
                return "[无法获取标题]"
            key = FIELDS["game_name"]
            title_prop = page["properties"][key]["title"]
            return "".join([part["text"]["content"] for part in title_prop])
        except Exception as e:
            logger.error(f"get_page_title error: {e}")
            return "[无法获取标题]"

    async def search_game(self, title):
        url = f"https://api.notion.com/v1/databases/{self.game_db_id}/query"
        payload = {"filter": {"property": FIELDS["game_name"], "title": {"equals": title}}}
        resp = await self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    async def check_page_exists(self, page_id):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        try:
            res = await self.client.get(url, headers=self.headers, timeout=10)
            if res.status_code in {404, 403}:
                return False
            data = res.json()
            return not data.get("archived", False)
        except Exception:
            return False

    async def search_brand(self, brand_name):
        url = f"https://api.notion.com/v1/databases/{self.brand_db_id}/query"
        payload = {"filter": {"property": FIELDS["brand_name"], "title": {"equals": brand_name}}}
        resp = await self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    async def get_all_game_titles(self):
        url = f"https://api.notion.com/v1/databases/{self.game_db_id}/query"
        all_games = []
        next_cursor = None
        while True:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            resp = await self._request("POST", url, payload)
            if not resp:
                break
            results = resp.get("results", [])
            for page in results:
                props = page.get("properties", {})
                title_data = props.get(FIELDS["game_name"], {}).get("title", [])
                title = "".join([t.get("plain_text", "") for t in title_data]).strip()
                if title:
                    all_games.append({"title": title, "id": page["id"]})
            if resp.get("has_more"):
                next_cursor = resp.get("next_cursor")
            else:
                break
        return all_games

    async def get_database_schema(self, db_id: str):
        url = f"https://api.notion.com/v1/databases/{db_id}"
        return await self._request("GET", url)

    # --- 核心改动：支持更多常用类型 ---
    async def add_new_property_to_db(
        self, db_id: str, prop_name: str, prop_type: str = "rich_text"
    ) -> bool:
        """向指定的数据库添加一个指定类型的新属性"""
        url = f"https://api.notion.com/v1/databases/{db_id}"

        prop_payload = {}
        if prop_type in ["rich_text", "number", "date", "url", "files", "checkbox"]:
            prop_payload = {prop_type: {}}
        elif prop_type == "select":
            prop_payload = {"select": {"options": []}}
        elif prop_type == "multi_select":
            prop_payload = {"multi_select": {"options": []}}
        else:  # 默认为 rich_text
            prop_type = "rich_text"
            prop_payload = {"rich_text": {}}

        payload = {"properties": {prop_name: prop_payload}}

        logger.system(
            f"正在尝试向 Notion 数据库 ({db_id[-5:]}) 添加新属性 '{prop_name}' (类型: {prop_type})..."
        )
        response = await self._request("PATCH", url, payload)
        if response:
            logger.success(f"成功向 Notion 添加了新属性: '{prop_name}'")
            return True
        else:
            logger.error(f"向 Notion 添加新属性 '{prop_name}' 失败。请检查 API Token 权限。")
            return False

    # --- 核心改动结束 ---

    async def create_or_update_game(self, info, brand_relation_id=None, page_id=None):
        title = info.get("title") or info.get(FIELDS["game_name"])
        if not page_id:
            existing = await self.search_game(title)
            page_id = existing[0]["id"] if existing else None
        props = {FIELDS["game_name"]: {"title": [{"text": {"content": title}}]}}
        if info.get("game_official_url"):
            props[FIELDS["game_official_url"]] = {"url": info["game_official_url"]}
        if info.get("dlsite_link"):
            props[FIELDS["dlsite_link"]] = {"url": info["dlsite_link"]}
        if info.get("getchu_link"):
            props[FIELDS["getchu_link"]] = {"url": info["getchu_link"]}
        if info.get("bangumi_url"):
            props[FIELDS["bangumi_url"]] = {"url": info["bangumi_url"]}
        if info.get("游戏别名"):
            props[FIELDS["game_alias"]] = {"rich_text": [{"text": {"content": info["游戏别名"]}}]}
        if info.get("大小"):
            props[FIELDS["game_size"]] = {"rich_text": [{"text": {"content": info["大小"]}}]}
        iso_date = convert_date_jp_to_iso(info.get("发售日"))
        if iso_date:
            props[FIELDS["release_date"]] = {"date": {"start": iso_date}}
        for key, field_key in [
            ("剧本", "script"),
            ("原画", "illustrator"),
            ("声优", "voice_actor"),
            ("音乐", "music"),
        ]:
            val = info.get(key)
            if val:
                props[FIELDS[field_key]] = {"multi_select": [{"name": v} for v in val if v.strip()]}
        if info.get("作品形式"):
            props[FIELDS["game_type"]] = {
                "multi_select": [{"name": t} for t in info["作品形式"] if t.strip()]
            }
        if info.get("标签"):
            props[FIELDS["tags"]] = {
                "multi_select": [{"name": t} for t in info["标签"] if t.strip()]
            }
        price_raw = info.get("价格")
        if price_raw and price_raw != "无":
            try:
                price_num = float(re.sub(r"[^\d.]", "", price_raw))
                props[FIELDS["price"]] = {"number": price_num}
            except (ValueError, TypeError):
                pass
        if info.get("封面图链接"):
            props[FIELDS["cover_image"]] = {
                "files": [
                    {"type": "external", "name": "cover", "external": {"url": info["封面图链接"]}}
                ]
            }
        if info.get("游戏简介"):
            props[FIELDS["game_summary"]] = {
                "rich_text": [{"text": {"content": info["游戏简介"][:2000]}}]
            }
        if brand_relation_id:
            props[FIELDS["brand_relation"]] = {"relation": [{"id": brand_relation_id}]}
        if info.get("资源链接"):
            props[FIELDS["resource_link"]] = {"url": info["资源链接"]}
        url = (
            f"https://api.notion.com/v1/pages/{page_id}"
            if page_id
            else "https://api.notion.com/v1/pages"
        )
        method = "PATCH" if page_id else "POST"
        payload = {"properties": props}
        if not page_id:
            payload["parent"] = {"database_id": self.game_db_id}
        resp = await self._request(method, url, payload)
        if resp:
            logger.success(f"{'已更新' if page_id else '已创建'}游戏: {title}")
            return resp.get("id")
        else:
            logger.error(f"提交游戏失败: {title}")
            return None

    async def create_or_update_brand(self, brand_name, **info):
        existing = await self.search_brand(brand_name)
        page_id = existing[0]["id"] if existing else None

        schema_data = await self.get_database_schema(self.brand_db_id)
        if not schema_data:
            logger.error("无法获取厂商数据库结构，无法更新品牌信息。")
            return None
        properties_schema = schema_data.get("properties", {})

        # 步骤 1: 将所有 info 中的内部键，映射到 Notion 字段名
        # 这是一个 key -> value 的映射，key是Notion字段名，value是对应的值
        notion_data_map = {
            FIELDS["brand_name"]: brand_name,
            FIELDS["brand_official_url"]: info.get("official_url"),
            FIELDS["brand_icon"]: info.get("icon_url"),
            FIELDS["brand_summary"]: info.get("summary"),
            FIELDS["brand_bangumi_url"]: info.get("bangumi_url"),
            FIELDS["brand_company_address"]: info.get("company_address"),
            FIELDS["brand_birthday"]: info.get("birthday"),
            FIELDS["brand_alias"]: info.get("alias"),
            FIELDS["brand_twitter"]: info.get("twitter"),
            FIELDS["brand_cien"]: info.get("ci_en_url"),
        }

        # 将 info 中所有其他未明确映射的键值对也添加进来
        # (例如未来新增的 'DLsite' 等)
        for key, value in info.items():
            if (
                key
                not in [
                    "official_url",
                    "icon_url",
                    "summary",
                    "bangumi_url",
                    "company_address",
                    "birthday",
                    "alias",
                    "twitter",
                    "ci_en_url",
                ]
                and value
            ):
                notion_data_map[key] = value

        # 步骤 2: 动态构建属性 payload
        props = {}
        for notion_prop_name, value in notion_data_map.items():
            if not value or not notion_prop_name:
                continue

            # 使用正确的 Notion 属性名进行查询
            prop_info = properties_schema.get(notion_prop_name)
            if not prop_info:
                logger.warn(f"属性 '{notion_prop_name}' 在厂商库中不存在，已跳过。")
                continue

            prop_type = prop_info.get("type")

            # 根据属性类型构建 payload (这部分逻辑不变)
            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}
            elif prop_type == "rich_text":
                val_str = "、".join(value) if isinstance(value, (list, set)) else str(value)
                props[notion_prop_name] = {"rich_text": [{"text": {"content": val_str}}]}
            elif prop_type == "url":
                props[notion_prop_name] = {"url": str(value)}
            elif prop_type == "files":
                props[notion_prop_name] = {
                    "files": [{"type": "external", "name": "icon", "external": {"url": str(value)}}]
                }
            elif prop_type == "select":
                props[notion_prop_name] = {"select": {"name": str(value)}}
            # ... 其他类型 ...

        # 步骤 3: 发送请求 (逻辑不变)
        if page_id:
            resp = await self._request(
                "PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"properties": props}
            )
            if resp:
                logger.info(f"已更新品牌页面: {brand_name}")
            return page_id if resp else None
        else:
            payload = {"parent": {"database_id": self.brand_db_id}, "properties": props}
            resp = await self._request("POST", "https://api.notion.com/v1/pages", payload)
            if resp:
                logger.success(f"新建品牌: {brand_name}")
            return resp.get("id") if resp else None
