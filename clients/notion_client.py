# clients/notion_client.py
import requests
import re
import difflib
from datetime import datetime
from utils.utils import convert_date_jp_to_iso
from config.config_fields import FIELDS

class NotionClient:
    def __init__(self, token, game_db_id, brand_db_id):
        self.token = token
        self.game_db_id = game_db_id
        self.brand_db_id = brand_db_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def _request(self, method, url, json_data=None):
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

    def search_game(self, title):
        url = f"https://api.notion.com/v1/databases/{self.game_db_id}/query"
        payload = {"filter": {"property": FIELDS["game_name"], "title": {"equals": title}}}
        resp = self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    def search_brand(self, brand_name):
        url = f"https://api.notion.com/v1/databases/{self.brand_db_id}/query"
        payload = {"filter": {"property": FIELDS["brand_name"], "title": {"equals": brand_name}}}
        resp = self._request("POST", url, payload)
        return resp.get("results", []) if resp else []

    def create_or_update_brand(self, brand_name, official_url=None, icon_url=None):
        existing = self.search_brand(brand_name)
        props = {FIELDS["brand_name"]: {"title": [{"text": {"content": brand_name}}]}}
        if existing:
            page_id = existing[0]["id"]
            current_props = existing[0]["properties"]

            if official_url and not current_props.get(FIELDS["brand_official_url"], {}).get("url"):
                props[FIELDS["brand_official_url"]] = {"url": official_url}

            if icon_url and not current_props.get(FIELDS["brand_icon"], {}).get("files"):
                props[FIELDS["brand_icon"]] = {
                    "files": [{"type": "external", "name": "icon", "external": {"url": icon_url}}]
                }

            if len(props) == 1:
                return page_id

            url = f"https://api.notion.com/v1/pages/{page_id}"
            self._request("PATCH", url, {"properties": props})
            print(f"🛠️ 已更新品牌页面: {brand_name}")
            return page_id
        else:
            if official_url:
                props[FIELDS["brand_official_url"]] = {"url": official_url}
            if icon_url:
                props[FIELDS["brand_icon"]] = {
                    "files": [{"type": "external", "name": "icon", "external": {"url": icon_url}}]
                }
            url = "https://api.notion.com/v1/pages"
            payload = {"parent": {"database_id": self.brand_db_id}, "properties": props}
            resp = self._request("POST", url, payload)
            if resp:
                print(f"✅ 新建品牌: {brand_name}")
                return resp.get("id")
        return None

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

        for key, field_key in [("剧本", "script"), ("原画", "illustrator"), ("声优", "voice_actor"), ("音乐", "music")]:
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
                "files": [{
                    "type": "external",
                    "name": "cover",
                    "external": {"url": info["封面图链接"]}
                }]
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
        else:
            print(f"❌ 提交游戏失败: {title}")

    def create_or_update_brand(self, brand_name, official_url=None, icon_url=None, summary=None, bangumi_url=None, company_address=None, birthday=None, alias=None, twitter=None):
        existing = self.search_brand(brand_name)
        props = {FIELDS["brand_name"]: {"title": [{"text": {"content": brand_name}}]}}

        if official_url:
            props[FIELDS["brand_official_url"]] = {"url": official_url}
        if icon_url:
            props[FIELDS["brand_icon"]] = {
                "files": [{"type": "external", "name": "icon", "external": {"url": icon_url}}]
            }
        if summary:
            props[FIELDS["brand_summary"]] = {"rich_text": [{"text": {"content": summary}}]}
        if bangumi_url:
            props[FIELDS["brand_bangumi_url"]] = {"url": bangumi_url}
        if company_address:
            props[FIELDS["brand_company_address"]] = {"rich_text": [{"text": {"content": company_address}}]}
        if birthday:
            props[FIELDS["brand_birthday"]] = {"rich_text": [{"text": {"content": birthday}}]}
        if alias:
            # 如果是列表，合并成字符串
            if isinstance(alias, (list, set)):
                alias_text = "、".join(alias)
            else:
                alias_text = str(alias)
            props[FIELDS["brand_alias"]] = {"rich_text": [{"text": {"content": alias_text}}]}
        if twitter:
            props[FIELDS["brand_twitter"]] = {"url": twitter}

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
