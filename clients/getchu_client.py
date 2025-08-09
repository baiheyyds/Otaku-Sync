# clients/getchu_client.py
# GetchuClient 类用于抓取 Getchu 网站的游戏信息
import random
import re
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from utils import logger


class GetchuClient:
    BASE_URL = "https://www.getchu.com"
    SEARCH_URL = "https://www.getchu.com/php/nsearch.phtml"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.headers = self._get_headers()
        self.cookies = {"getchu_adalt_flag": "getchu.com"}

    def _get_headers(self):
        return {
            "User-Agent": random.choice(
                [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
                ]
            ),
            "Referer": "https://www.getchu.com/",
        }

    async def search(self, keyword):
        logger.info(f"[Getchu] 开始搜索: {keyword}")
        try:
            safe_keyword = keyword.replace("～", "〜")
            encoded_keyword = quote(safe_keyword.encode("shift_jis", errors="ignore"))
            url = f"{self.SEARCH_URL}?genre=all&search_keyword={encoded_keyword}&check_key_dtl=1&submit="

            resp = await self.client.get(
                url, timeout=10, headers=self.headers, cookies=self.cookies
            )
            resp.raise_for_status()

            html_text = resp.content.decode("euc_jp", errors="ignore")
            soup = BeautifulSoup(html_text, "html.parser")

            result_ul = soup.find("ul", class_="display")

            if not result_ul or not isinstance(result_ul, Tag):
                logger.warn("[Getchu] 未找到搜索结果列表或页面结构异常。")
                return []

            items = []
            for li in result_ul.find_all("li"):
                block = li.select_one("#detail_block")
                if not block:
                    continue

                title_tag = block.select_one("a.blueb[href*='soft.phtml?id=']")
                if not title_tag:
                    continue

                item_type_tag = block.select_one("span.orangeb")
                item_type = item_type_tag.get_text(strip=True) if item_type_tag else "未知"

                price_tag = block.select_one(".redb")
                price_text = price_tag.get_text(strip=True) if price_tag else ""

                if not price_text:
                    for p in block.find_all("p", string=re.compile("定価")):
                        match = re.search(r"定価[:：]?\s*([^\s<（]+)", p.get_text())
                        if match:
                            price_text = match.group(1)
                            break

                game_id_match = re.search(r"id=(\d+)", title_tag["href"])
                if not game_id_match:
                    continue

                items.append(
                    {
                        "title": title_tag.get_text(strip=True),
                        "url": f"{self.BASE_URL}/soft.phtml?id={game_id_match.group(1)}",
                        "价格": price_text or "未知",
                        "类型": item_type,
                    }
                )

            items = [item for item in items if "ゲーム" in item.get("类型", "")]
            exclude_keywords = ["グッズ", "BOOKS", "CD", "音楽"]
            items = [
                item
                for item in items
                if not any(ex_kw in item.get("类型", "") for ex_kw in exclude_keywords)
            ]

            logger.success(f"找到 {len(items)} 个Getchu搜索结果。")
            return items

        except UnicodeEncodeError as ue:
            logger.error(f"[Getchu] 编码失败: {ue}")
            return []
        except Exception as e:
            logger.error(f"[Getchu] 搜索失败: {e}")
            return []

    async def get_game_detail(self, url):
        try:
            resp = await self.client.get(
                url, timeout=15, headers=self.headers, cookies=self.cookies
            )
            resp.raise_for_status()
            html_text = resp.content.decode("euc_jp", errors="ignore")
            soup = BeautifulSoup(html_text, "html.parser")

            if "年齢認証" in soup.title.text:
                logger.error("[Getchu] 绕过年龄验证失败，页面内容不正确。")
                return {}

            info_table = soup.find("table", id="soft_table")
            if not info_table:
                alt_table = soup.find("td", text=re.compile("ブランド"))
                if alt_table:
                    info_table = alt_table.find_parent("table")
                if not info_table:
                    logger.error("[Getchu] 未找到关键信息表格。")
                    return {}

            # --- 核心改动：移除对 class="right" 的依赖 ---

            def find_row_by_header(header_text: str) -> Tag | None:
                """根据表头文本查找并返回整行(tr)"""
                regex = re.compile(f"^{header_text}[：:]?\\s*$")
                # 不再需要 class_="right"，只根据文本内容查找
                header_td = info_table.find("td", string=regex)
                if header_td:
                    return header_td.find_parent("tr")
                return None

            brand, brand_site = None, None
            brand_row = find_row_by_header("ブランド")
            if brand_row and (value_td := brand_row.find_all("td")[-1]):
                a_tag = value_td.find("a", id="brandsite")
                if a_tag:
                    brand = a_tag.get_text(strip=True)
                    brand_site = a_tag.get("href")

            price = None
            price_row = find_row_by_header("定価")
            if price_row and (value_td := price_row.find_all("td")[-1]):
                full_price_text = value_td.get_text(strip=True)
                price = full_price_text.split("(")[0].strip()

            release_date = None
            date_row = find_row_by_header("発売日")
            if date_row and (value_td := date_row.find_all("td")[-1]):
                release_date = value_td.get_text(strip=True)

            def extract_multi_values(header_text: str) -> list[str]:
                """提取一个字段中的多个链接文本值"""
                row = find_row_by_header(header_text)
                if row and (value_td := row.find_all("td")[-1]):
                    return [a.get_text(strip=True) for a in value_td.find_all("a")]
                return []

            illustrators = extract_multi_values("原画")
            scenarists = extract_multi_values("シナリオ")

            cover_a = soup.select_one("a.highslide[href*='/graphics/']")
            raw_image_url = (
                urljoin(self.BASE_URL, cover_a["href"]) if cover_a and cover_a.img else None
            )
            image_url = (
                raw_image_url.replace("https://www.getchu.com", "https://cover.ydgal.com")
                if raw_image_url
                else None
            )

            title_tag = soup.select_one("#soft-title")
            title = (
                title_tag.get_text(strip=True).replace("Getchu.com：", "")
                if title_tag
                else "未知标题"
            )

            return {
                "封面图链接": image_url,
                "标题": title,
                "品牌": brand,
                "品牌官网": brand_site,
                "发售日": release_date,
                "价格": price,
                "原画": illustrators,
                "剧本": scenarists,
            }
        except Exception as e:
            logger.error(f"[Getchu] (httpx)抓取详情失败: {e}", exc_info=True)
            return {}
