# clients/notion_client.py
# 该模块用于与 Notion API 交互，处理游戏和品牌数据的
import difflib
import re
import time
from datetime import datetime

import requests

from config.config_fields import FIELDS
from utils.utils import convert_date_jp_to_iso


class NotionClient:
    def __init__(self, token, game_db_id, brand_db_id):
        self.token = token
        self.game_db_id = game_db_id
        self.brand_db_id = brand_db_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _raw_request(self, method, url, json_data=None):
        try:
            if method == "POST":
                r = requests.post(url, headers=self.headers, json=json_data, timeout=10)
            elif method == "PATCH":
                r = requests.patch(url, headers=self.headers, json=json_data, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"Notion API request failed: {e}")
            return None

    def _request(self, method, url, json_data=None, retries=3, delay=2):
        for attempt in range(retries):
            resp = self._raw_request(method, url, json_data)
            if resp is not None:
                return resp
            if attempt < retries - 1:
                print(f"🔁 重试 Notion API ({attempt + 1}/{retries})...")
                time.sleep(delay)
        print("⛔ 最终重试失败，跳过该请求")
        return None

    def get_page_title(self, page):
        try:
            if "properties" not in page:
                print(f"DEBUG get_page_title page missing properties: {page.keys()}")
                return "[无法获取标题]"
            key = FIELDS["game_name"]
            title_prop = page["properties"][key]["title"]
            return "".join([part["text"]["content"] for part in title_prop])
        except Exception as e:
            print("DEBUG get_page_title input keys:", list(page.keys()))
            print("DEBUG get_page_title properties keys:", list(page.get("properties", {}).keys()))
            print(f"get_page_title error: {e}")
            return "[无法获取标题]"


    def search_game(self, title):
        url = f"https://api.notion.com/v1/databases/{self.game_db_id}/query"
        payload = {"filter": {"property": FIELDS["game_name"], "title": {"equals": title}}}
        resp = self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    def check_page_exists(self, page_id):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 404 or res.status_code == 403:
                return False
            data = res.json()
            return not data.get("archived", False)
        except Exception:
            return False


    def search_brand(self, brand_name):
        url = f"https://api.notion.com/v1/databases/{self.brand_db_id}/query"
        payload = {
            "filter": {
                "property": FIELDS["brand_name"],
                "title": {"equals": brand_name},
            }
        }
        resp = self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    def get_all_game_titles(self):
        url = f"https://api.notion.com/v1/databases/{self.game_db_id}/query"
        all_games = []
        next_cursor = None
        while True:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            resp = self._request("POST", url, payload)
            if not resp:
                break
            results = resp.get("results", [])
            for page in results:
                props = page.get("properties", {})
                title_data = props.get(FIELDS["game_name"], {}).get("title", [])
                title = "".join([t.get("plain_text", "") for t in title_data]).strip()
                if title:  # 只收集非空标题
                    all_games.append({"title": title, "id": page["id"]})
            if resp.get("has_more"):
                next_cursor = resp.get("next_cursor")
            else:
                break
        return all_games

    def find_similar_games(self, title, threshold=0.85):
        existing = self.get_all_game_titles()
        similar = []
        title_norm = title.lower().strip()
        for game in existing:
            game_title_norm = game["title"].lower().strip()
            ratio = difflib.SequenceMatcher(None, title_norm, game_title_norm).ratio()
            if ratio >= threshold:
                similar.append(game)
        return similar

    def create_or_update_game(self, info, brand_relation_id=None, page_id=None):
        title = info.get("title") or info.get(FIELDS["game_name"])
        if not page_id:
            existing = self.search_game(title)
            page_id = existing[0]["id"] if existing else None

        props = {
            FIELDS["game_name"]: {"title": [{"text": {"content": title}}]},
            FIELDS["game_url"]: {"url": info.get("url")},
        }

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

        work_types = info.get("作品形式")
        if work_types:
            props[FIELDS["game_type"]] = {"multi_select": [{"name": t} for t in work_types if t.strip()]}

        tags = info.get("标签")
        if tags and isinstance(tags, (list, set)):
            props[FIELDS["tags"]] = {"multi_select": [{"name": t} for t in tags if t.strip()]}

        price_raw = info.get("价格")
        if price_raw and price_raw != "无":
            try:
                price_num = float(re.sub(r"[^\d.]", "", price_raw))
                props[FIELDS["price"]] = {"number": price_num}
            except:
                pass

        if info.get("封面图链接"):
            props[FIELDS["cover_image"]] = {
                "files": [
                    {
                        "type": "external",
                        "name": "cover",
                        "external": {"url": info["封面图链接"]},
                    }
                ]
            }

        if brand_relation_id:
            props[FIELDS["brand_relation"]] = {"relation": [{"id": brand_relation_id}]}

        if info.get("资源链接"):
            props[FIELDS["resource_link"]] = {"url": info["资源链接"]}

        url = f"https://api.notion.com/v1/pages/{page_id}" if page_id else "https://api.notion.com/v1/pages"
        method = "PATCH" if page_id else "POST"
        payload = {"properties": props}
        if not page_id:
            payload["parent"] = {"database_id": self.game_db_id}

        resp = self._request(method, url, payload)
        if resp:
            print(f"✅ {'已更新' if page_id else '已创建'}游戏: {title}")
            return resp.get("id")  # 返回页面ID
        else:
            print(f"❌ 提交游戏失败: {title}")

    def create_or_update_brand(
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
    ):
        existing = self.search_brand(brand_name)
        props = {FIELDS["brand_name"]: {"title": [{"text": {"content": brand_name}}]}}

        def add_url_field(field_key, value):
            if value:
                props[field_key] = {"url": value}

        def add_rich_text_field(field_key, value):
            if value:
                props[field_key] = {"rich_text": [{"text": {"content": value}}]}

        def add_files_field(field_key, url):
            if url:
                props[field_key] = {"files": [{"type": "external", "name": "icon", "external": {"url": url}}]}

        add_url_field(FIELDS["brand_official_url"], official_url)
        add_files_field(FIELDS["brand_icon"], icon_url)
        add_rich_text_field(FIELDS["brand_summary"], summary)
        add_url_field(FIELDS["brand_bangumi_url"], bangumi_url)
        add_rich_text_field(FIELDS["brand_company_address"], company_address)
        add_rich_text_field(FIELDS["brand_birthday"], birthday)
        if alias:
            if isinstance(alias, (list, set)):
                alias_text = "、".join(alias)
            else:
                alias_text = str(alias)
            add_rich_text_field(FIELDS["brand_alias"], alias_text)
        add_url_field(FIELDS["brand_twitter"], twitter)

        if existing:
            page_id = existing[0]["id"]
            url = f"https://api.notion.com/v1/pages/{page_id}"
            resp = self._request("PATCH", url, {"properties": props})
            if resp:
                print(f"🛠️ 已更新品牌页面: {brand_name}")
                return page_id
            else:
                print(f"❌ 更新品牌失败: {brand_name}")
                return None
        else:
            url = "https://api.notion.com/v1/pages"
            payload = {"parent": {"database_id": self.brand_db_id}, "properties": props}
            resp = self._request("POST", url, payload)
            if resp:
                print(f"✅ 新建品牌: {brand_name}")
                return resp.get("id")
            else:
                print(f"❌ 创建品牌失败: {brand_name}")
                return None
