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

    async def get_all_pages_from_db(self, db_id: str):
        """从指定数据库获取所有页面的完整对象。"""
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        all_pages = []
        next_cursor = None
        while True:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            resp = await self._request("POST", url, payload)
            if not resp:
                logger.error(f"无法从数据库 {db_id} 获取页面，流程中止。")
                break

            results = resp.get("results", [])
            all_pages.extend(results)

            if resp.get("has_more"):
                next_cursor = resp.get("next_cursor")
            else:
                break
        return all_pages

    async def get_page(self, page_id: str):
        """根据页面ID获取完整的页面对象"""
        url = f"https://api.notion.com/v1/pages/{page_id}"
        return await self._request("GET", url)

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

    async def create_or_update_game(self, properties_schema: dict, page_id=None, **info):
        title = info.get("title")
        if not title:
            logger.error("游戏标题为空,无法创建或更新.")
            return None

        if not page_id:
            existing = await self.search_game(title)
            page_id = existing[0]["id"] if existing else None

        data_for_notion = {}
        for prop_name in properties_schema:
            if prop_name in info and info[prop_name] is not None:
                data_for_notion[prop_name] = info[prop_name]

        source_to_notion_map = {
            "title": FIELDS["game_name"],
            "title_cn": FIELDS["game_alias"],
            "summary": FIELDS["game_summary"],
            "url": FIELDS["bangumi_url"],
            "封面图链接": FIELDS["cover_image"],
            "发售日": FIELDS["release_date"],
            "剧本": FIELDS["script"],
            "原画": FIELDS["illustrator"],
            "声优": FIELDS["voice_actor"],
            "音乐": FIELDS["music"],
            "作品形式": FIELDS["game_type"],
            "大小": FIELDS["game_size"],
            "标签": FIELDS["tags"],
            "价格": FIELDS["price"],
            "dlsite_link": FIELDS["dlsite_link"],
            "fanza_link": FIELDS["fanza_link"],
            "资源链接": FIELDS["resource_link"],
            "brand_relation_id": FIELDS["brand_relation"],
        }

        # --- [ULTIMATE FIX: Proactive Data Cleansing during Merge] ---
        for source_key, notion_key in source_to_notion_map.items():
            if source_key in info and info[source_key] is not None:
                new_value = info[source_key]

                # Proactively filter empty strings from the new value
                if isinstance(new_value, list):
                    new_value = [v for v in new_value if v]
                elif not new_value:  # If new_value is ""
                    continue  # Skip this empty value entirely

                current_values = data_for_notion.get(notion_key)
                if current_values:
                    if not isinstance(current_values, list):
                        current_values = [current_values]
                    if not isinstance(new_value, list):
                        new_value = [new_value]

                    combined = current_values + new_value

                    # Filter again after combining, then unique
                    unique_values = []
                    seen_hashable = set()
                    for item in combined:
                        if not item:
                            continue  # Final check for empty strings/None
                        try:
                            if item not in seen_hashable:
                                unique_values.append(item)
                                seen_hashable.add(item)
                        except TypeError:
                            unique_values.append(item)
                    data_for_notion[notion_key] = unique_values
                elif new_value:  # Only assign if the new value is not empty
                    data_for_notion[notion_key] = new_value
        # --- [FIX ENDS] ---

        if title:
            data_for_notion[FIELDS["game_name"]] = title

        props = {}
        for notion_prop_name, value in data_for_notion.items():
            if value is None:
                continue
            if isinstance(value, (str, list, dict)) and not value:
                continue

            prop_info = properties_schema.get(notion_prop_name)
            if not prop_info:
                logger.warn(f"属性 '{notion_prop_name}' 在游戏库中不存在,已跳过.")
                continue
            prop_type = prop_info.get("type")

            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}

            elif prop_type == "rich_text":
                content = ""
                if isinstance(value, (list, set)):
                    unique_values = []
                    seen_hashable = set()
                    for item in value:
                        if not item:
                            continue  # Final gatekeeper check
                        try:
                            if item not in seen_hashable:
                                unique_values.append(item)
                                seen_hashable.add(item)
                        except TypeError:
                            unique_values.append(item)

                    formatted_values = []
                    for item in unique_values:
                        if not item:
                            continue  # Paranoid final check
                        if isinstance(item, dict):
                            lines = [f"🔹 {k}: {v}" for k, v in item.items()]
                            formatted_values.append("\n".join(lines))
                        else:
                            formatted_values.append(f"🔹 {str(item)}")
                    content = "\n".join(formatted_values)

                elif isinstance(value, dict):
                    lines = [f"🔹 {k}: {v}" for k, v in value.items()]
                    content = "\n".join(lines)
                else:
                    content = str(value)

                if content:
                    props[notion_prop_name] = {"rich_text": [{"text": {"content": content[:2000]}}]}

            elif prop_type in ("url", "date", "number", "files", "select"):
                final_value = value
                if isinstance(value, dict):
                    final_value = next(iter(value.values()), None)
                elif isinstance(value, list):
                    final_value = value[0] if value else None

                if prop_type == "url" and final_value:
                    props[notion_prop_name] = {"url": str(final_value)}
                elif prop_type == "date":
                    if iso_date := convert_date_jp_to_iso(str(final_value)):
                        props[notion_prop_name] = {"date": {"start": iso_date}}
                elif prop_type == "number":
                    try:
                        if final_value:
                            props[notion_prop_name] = {
                                "number": float(re.sub(r"[^\d.]", "", str(final_value)))
                            }
                    except (ValueError, TypeError):
                        pass
                elif prop_type == "files" and final_value:
                    props[notion_prop_name] = {
                        "files": [
                            {
                                "type": "external",
                                "name": "cover",
                                "external": {"url": str(final_value)},
                            }
                        ]
                    }
                elif prop_type == "select" and str(final_value).strip():
                    props[notion_prop_name] = {"select": {"name": str(final_value)}}

            elif prop_type == "relation":
                if value:
                    props[notion_prop_name] = {"relation": [{"id": str(value)}]}

            elif prop_type == "multi_select":
                options = []
                values_to_process = value if isinstance(value, list) else [value]

                for item in values_to_process:
                    if isinstance(item, str):
                        split_items = [
                            v.strip() for v in re.split(r"[、・,／/;]+", item) if v.strip()
                        ]
                        options.extend(split_items)
                    elif item:
                        options.append(str(item))

                if options:
                    unique_options = list(dict.fromkeys(options))
                    props[notion_prop_name] = {
                        "multi_select": [{"name": str(opt)} for opt in unique_options]
                    }

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

        # 准备一个字典，用来存放所有要提交给 Notion 的数据
        # 键是 Notion 属性名，值是对应的数据
        data_to_build = {}

        # 1. 首先处理标准化的、预先定义好的字段
        # 这个映射将我们内部的 key (如 'official_url') 转换为 Notion 的属性名
        standard_key_map = {
            "official_url": FIELDS["brand_official_url"],
            "icon_url": FIELDS["brand_icon"],
            "summary": FIELDS["brand_summary"],
            "bangumi_url": FIELDS["brand_bangumi_url"],
            "twitter": FIELDS["brand_twitter"],
            "ci_en_url": FIELDS["brand_cien"],
        }

        for info_key, notion_prop in standard_key_map.items():
            if info_key in info and info[info_key]:
                data_to_build[notion_prop] = info[info_key]

        # 2. 处理那些动态添加的、key 和 Notion 属性名一致的字段
        # 比如 "成立时间", "公司地址", "别名" 等
        for key, value in info.items():
            # 如果 key 已经是 Notion 属性名 (且不在上面的 map 里)，就直接用
            if key not in standard_key_map and key in properties_schema:
                if value:
                    data_to_build[key] = value

        # 3. 不要忘记最重要的主标题
        data_to_build[FIELDS["brand_name"]] = brand_name

        # 4. 动态构建最终的 props payload
        props = {}
        for notion_prop_name, value in data_to_build.items():
            # 跳过空值和不存在的属性
            if value is None or notion_prop_name not in properties_schema:
                if notion_prop_name not in properties_schema:
                    logger.warn(f"属性 '{notion_prop_name}' 在厂商库中不存在，已跳过。")
                continue

            prop_type = properties_schema.get(notion_prop_name, {}).get("type")

            # 根据属性类型格式化数据
            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}
            elif prop_type == "rich_text":
                # 如果值是列表（比如别名），就用 '、' 连接
                val_str = "、".join(value) if isinstance(value, (list, set)) else str(value)
                props[notion_prop_name] = {"rich_text": [{"text": {"content": val_str[:2000]}}]}
            elif prop_type == "url":
                props[notion_prop_name] = {"url": str(value)}
            elif prop_type == "files":
                props[notion_prop_name] = {
                    "files": [{"type": "external", "name": "icon", "external": {"url": str(value)}}]
                }
            elif prop_type == "select":
                if str(value).strip():
                    props[notion_prop_name] = {"select": {"name": str(value)}}

        # 发送请求 (这部分逻辑不变)
        if not props:
            logger.warn(f"没有可为品牌 '{brand_name}' 更新的数据，跳过。")
            return page_id if page_id else None

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
