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
            logger.error(f"Notion API request failed: {e}")
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

    # ... get_page_title, search_game, check_page_exists, search_brand, get_all_game_titles 无变化 ...
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

    async def create_or_update_game(self, info, brand_relation_id=None, page_id=None):
        title = info.get("title") or info.get(FIELDS["game_name"])
        if not page_id:
            existing = await self.search_game(title)
            page_id = existing[0]["id"] if existing else None

        props = {FIELDS["game_name"]: {"title": [{"text": {"content": title}}]}}

        # --- 核心改动：支持写入新字段 ---
        if info.get("game_official_url"):
            props[FIELDS["game_official_url"]] = {"url": info["game_official_url"]}
        if info.get("dlsite_link"):
            props[FIELDS["dlsite_link"]] = {"url": info["dlsite_link"]}
        if info.get("getchu_link"):
            props[FIELDS["getchu_link"]] = {"url": info["getchu_link"]}
        if info.get("bangumi_url"):
            props[FIELDS["bangumi_url"]] = {"url": info["bangumi_url"]}
        # --- 核心改动结束 ---

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

    async def create_or_update_brand(
        self,
        brand_name,
        official_url=None,
        icon_url=None,
        summary=None,
        bangumi_url=None,
        company_address=None,
        birthday=None,
        alias=None,
        twitter=None,
        ci_en_url=None,  # <- 新增参数
    ):
        existing = await self.search_brand(brand_name)
        page_id = existing[0]["id"] if existing else None

        props = {FIELDS["brand_name"]: {"title": [{"text": {"content": brand_name}}]}}

        # --- 核心改动：支持写入 Ci-en 字段 ---
        if official_url:
            props[FIELDS["brand_official_url"]] = {"url": official_url}
        if ci_en_url:
            props[FIELDS["brand_cien"]] = {"url": ci_en_url}
        # --- 核心改动结束 ---

        if icon_url:
            props[FIELDS["brand_icon"]] = {
                "files": [{"type": "external", "name": "icon", "external": {"url": icon_url}}]
            }
        if summary:
            props[FIELDS["brand_summary"]] = {"rich_text": [{"text": {"content": summary}}]}
        if bangumi_url:
            props[FIELDS["brand_bangumi_url"]] = {"url": bangumi_url}
        if company_address:
            props[FIELDS["brand_company_address"]] = {
                "rich_text": [{"text": {"content": company_address}}]
            }
        if birthday:
            props[FIELDS["brand_birthday"]] = {"rich_text": [{"text": {"content": birthday}}]}
        if twitter:
            props[FIELDS["brand_twitter"]] = {"url": twitter}
        if alias:
            alias_text = "、".join(alias) if isinstance(alias, (list, set)) else str(alias)
            props[FIELDS["brand_alias"]] = {"rich_text": [{"text": {"content": alias_text}}]}

        if page_id:
            resp = await self._request(
                "PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"properties": props}
            )
            if resp:
                logger.info(f"已更新品牌页面: {brand_name}")
                return page_id
            else:
                logger.error(f"更新品牌失败: {brand_name}")
                return None
        else:
            payload = {"parent": {"database_id": self.brand_db_id}, "properties": props}
            resp = await self._request("POST", "https://api.notion.com/v1/pages", payload)
            if resp:
                logger.success(f"新建品牌: {brand_name}")
                return resp.get("id")
            else:
                logger.error(f"创建品牌失败: {brand_name}")
                return None
