# clients/notion_client.py
# 该模块用于与 Notion API 交互，处理游戏和品牌数据的
import asyncio
import re
import time
from datetime import datetime

import httpx

from config.config_fields import FIELDS
from utils import logger
from utils.utils import convert_date_jp_to_iso, normalize_brand_name


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
        self._all_brands_cache = None

    async def _request(self, method, url, json_data=None):
        max_retries = 3
        for attempt in range(max_retries):
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
            except httpx.HTTPStatusError as e:
                # 对于HTTP错误，记录更详细的响应信息, 这种错误通常不应该重试
                logger.error(f"Notion API 请求失败: {e}. 响应: {e.response.text}")
                return None
            except (httpx.ReadError, httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                # 对于这些可恢复的网络错误，进行重试
                logger.warn(f"Notion API 网络错误 (尝试 {attempt + 1}/{max_retries}): {e.__class__.__name__}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))  # 逐渐增加等待时间
                    continue
                else:
                    logger.error(f"Notion API 请求在 {max_retries} 次尝试后最终失败。")
                    raise  # 在最后一次尝试失败后，重新引发异常
            except httpx.RequestError as e:
                # 对于其他网络层面的错误, 记录并重新抛出
                logger.error(f"Notion API 网络请求失败: {e.__class__.__name__} - {e}. 请求: {e.request.method} {e.request.url}")
                raise
            except Exception as e:
                # 其他未知异常
                logger.error(f"Notion API 未知错误: {e}")
                return None
        return None

    def get_page_title(self, page: dict) -> str:
        """
        [已升级] 通用页面标题获取函数。
        自动查找任何 Notion 页面中类型为 'title' 的主属性并返回其内容。
        """
        try:
            if "properties" not in page:
                return "[无法获取标题：页面缺少 properties]"

            # 遍历所有属性，找到类型为 'title' 的那一个
            for prop_name, prop_data in page["properties"].items():
                if prop_data.get("type") == "title":
                    title_list = prop_data.get("title", [])
                    if title_list:
                        return "".join([part.get("plain_text", "") for part in title_list])

            return "[无法获取标题：未找到 title 类型的属性]"
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
            # 这个请求只是为了检查存在性，不需要走全局的重试逻辑，可以设置一个较短的超时
            res = await self.client.get(url, headers=self.headers, timeout=10)
            if res.status_code in {404, 403}:
                return False
            data = res.json()
            return not data.get("archived", False)
        except Exception:
            return False

    async def get_all_brands(self, silent: bool = False) -> list[dict]:
        """
        获取所有品牌及其核心信息（名称、ID、是否有图标），用于缓存预热。
        该方法会直接从数据库查询结果中解析，避免对每个页面进行独立请求。
        """
        if self._all_brands_cache is not None:
            return self._all_brands_cache

        if not silent:
            logger.info("正在从 Notion 获取所有品牌信息用于预热缓存...")
            
        all_pages = await self.get_all_pages_from_db(self.brand_db_id)
        brands = []
        for page in all_pages:
            properties = page.get("properties", {})
            
            # 提取品牌名称
            title_prop = properties.get(FIELDS["brand_name"], {})
            title_list = title_prop.get("title", [])
            name = "".join([part.get("plain_text", "") for part in title_list]).strip()
            
            if not name:
                continue

            # 检查是否有图标
            icon_prop = properties.get(FIELDS["brand_icon"], {})
            has_icon = bool(icon_prop.get("files"))

            brands.append({
                "name": name,
                "page_id": page["id"],
                "has_icon": has_icon,
            })
        
        self._all_brands_cache = brands
        if not silent:
            logger.success(f"品牌缓存预热：成功获取到 {len(brands)} 个品牌的信息。")
        return brands

    async def get_brand_details_by_name(self, name: str) -> dict | None:
        """根据品牌名称查找品牌，并返回其ID和图标状态。"""
        if not name:
            return None
        
        normalized_name_to_find = normalize_brand_name(name)
        
        # 尝试从内存缓存获取（如果已填充）
        if self._all_brands_cache:
            for brand in self._all_brands_cache:
                if normalize_brand_name(brand.get("name", "")) == normalized_name_to_find:
                    return {"page_id": brand["page_id"], "has_icon": brand["has_icon"]}

        # 如果缓存未命中，执行单次精确查询
        url = f"https://api.notion.com/v1/databases/{self.brand_db_id}/query"
        payload = {"filter": {"property": FIELDS["brand_name"], "title": {"equals": name}}}
        resp = await self._request("POST", url, payload)

        if resp and resp.get("results"):
            page = resp["results"][0]
            properties = page.get("properties", {})
            icon_prop = properties.get(FIELDS["brand_icon"], {})
            has_icon = bool(icon_prop.get("files"))
            return {"page_id": page["id"], "has_icon": has_icon}
            
        return None

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

    async def get_all_pages_from_db(self, db_id: str) -> list:
        """获取指定数据库中的所有页面，自动处理分页。"""
        all_pages = []
        next_cursor = None
        url = f"https://api.notion.com/v1/databases/{db_id}/query"

        while True:
            payload = {"start_cursor": next_cursor} if next_cursor else {}
            resp = await self._request("POST", url, payload)
            if not resp:
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

    async def add_new_property_to_db(
        self,
        db_id: str,
        prop_name: str,
        prop_type: str = "rich_text"
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
        else:
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

        for source_key, notion_key in source_to_notion_map.items():
            if source_key in info and info[source_key] is not None:
                new_value = info[source_key]

                if isinstance(new_value, list):
                    new_value = [v for v in new_value if v]
                elif not new_value:
                    continue

                current_values = data_for_notion.get(notion_key)
                if current_values:
                    if not isinstance(current_values, list):
                        current_values = [current_values]
                    if not isinstance(new_value, list):
                        new_value = [new_value]

                    combined = current_values + new_value

                    unique_values = []
                    seen_hashable = set()
                    for item in combined:
                        if not item:
                            continue
                        try:
                            if item not in seen_hashable:
                                unique_values.append(item)
                                seen_hashable.add(item)
                        except TypeError:
                            unique_values.append(item)
                    data_for_notion[notion_key] = unique_values
                elif new_value:
                    data_for_notion[notion_key] = new_value

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
                            continue
                        try:
                            if item not in seen_hashable:
                                unique_values.append(item)
                                seen_hashable.add(item)
                        except TypeError:
                            unique_values.append(item)

                    formatted_values = []
                    for item in unique_values:
                        if not item:
                            continue
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
                            # 修正: 正则表达式移除所有非数字和非小数点的字符
                            cleaned_value = re.sub(r"[^\d.]", "", str(final_value))
                            if cleaned_value:
                                props[notion_prop_name] = {"number": float(cleaned_value)}
                    except (ValueError, TypeError):
                        # 如果转换失败（例如，值是“多人”），则忽略此属性
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

                # For tags, trust the TagManager and don't split further.
                if notion_prop_name == FIELDS["tags"]:
                    for item in values_to_process:
                        if item:
                            options.append(str(item))
                else:
                    # For other multi-selects, use a smart splitting heuristic.
                    for item in values_to_process:
                        if not isinstance(item, str):
                            if item:
                                options.append(str(item))
                            continue

                        # Heuristic: Only split by '/' if it doesn't create very short segments.
                        # This helps differentiate "Artist A / Artist B" from "Windows 7 / 8".
                        use_slash_as_separator = True
                        if '/' in item:
                            # Threshold for a segment to be considered "too short"
                            MIN_SEGMENT_LEN = 3 
                            if any(len(part.strip()) < MIN_SEGMENT_LEN for part in item.split('/')):
                                use_slash_as_separator = False

                        # Standardize separators
                        processed_item = item.replace('，', ',').replace('、', ',')
                        if use_slash_as_separator:
                            processed_item = processed_item.replace('/', ',')
                        
                        options.extend([opt.strip() for opt in processed_item.split(',') if opt.strip()])

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
            logger.success(f"{ '已更新' if page_id else '已创建'}游戏: {title}")
            return resp.get("id")
        else:
            logger.error(f"提交游戏失败: {title}")
            return None

    async def create_or_update_brand(self, brand_name, page_id=None, **info):
        if not page_id:
            brand_details = await self.get_brand_details_by_name(brand_name)
            if brand_details:
                page_id = brand_details.get("id")

        schema_data = await self.get_database_schema(self.brand_db_id)
        if not schema_data:
            logger.error("无法获取厂商数据库结构，无法更新品牌信息。")
            return None
        properties_schema = schema_data.get("properties", {})

        data_to_build = {}
        standard_key_map = {
            "official_url": FIELDS["brand_official_url"],
            "icon_url": FIELDS["brand_icon"],
            "summary": FIELDS["brand_summary"],
            "bangumi_url": FIELDS["brand_bangumi_url"],
            "twitter": FIELDS["brand_twitter"],
            "ci_en_url": FIELDS["brand_cien"],
            "icon": FIELDS["brand_icon"],
        }

        for info_key, notion_prop in standard_key_map.items():
            if info_key in info and info[info_key]:
                data_to_build[notion_prop] = info[info_key]

        for key, value in info.items():
            if key not in standard_key_map and key in properties_schema:
                if value:
                    data_to_build[key] = value

        data_to_build[FIELDS["brand_name"]] = brand_name

        props = {}
        for notion_prop_name, value in data_to_build.items():
            if value is None or notion_prop_name not in properties_schema:
                if notion_prop_name not in properties_schema:
                    logger.warn(f"属性 '{notion_prop_name}' 在厂商库中不存在，已跳过。")
                continue

            prop_type = properties_schema.get(notion_prop_name, {}).get("type")

            if prop_type == "title":
                props[notion_prop_name] = {"title": [{"text": {"content": str(value)}}]}

            elif prop_type == "rich_text":
                content = ""
                if isinstance(value, (list, set)):
                    formatted_values = [f"🔹 {str(item)}" for item in value if item]
                    content = "\n".join(formatted_values)
                elif isinstance(value, dict):
                    lines = [f"🔹 {k}: {v}" for k, v in value.items() if v]
                    content = "\n".join(lines)
                else:
                    content = str(value)

                if content:
                    props[notion_prop_name] = {"rich_text": [{"text": {"content": content[:2000]}}]}

            elif prop_type == "url":
                props[notion_prop_name] = {"url": str(value)}
            elif prop_type == "files":
                props[notion_prop_name] = {
                    "files": [{"type": "external", "name": "icon", "external": {"url": str(value)}}]
                }
            elif prop_type == "select":
                if str(value).strip():
                    props[notion_prop_name] = {"select": {"name": str(value)}}

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
