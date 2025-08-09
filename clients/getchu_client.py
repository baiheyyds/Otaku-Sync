# clients/getchu_client.py
# GetchuClient 类用于抓取 Getchu 网站的游戏信息
import random
import re
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from utils import logger


class GetchuClient:
    BASE_URL = "https://www.getchu.com"
    SEARCH_URL = "https://www.getchu.com/php/nsearch.phtml"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.client.headers.update(self._get_headers())
        self.client.cookies.set(name="getchu_adalt_flag", value="getchu.com", domain=".getchu.com")

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

            resp = await self.client.get(url, timeout=10)
            resp.raise_for_status()

            # Getchu 使用 EUC-JP 编码
            html_text = resp.content.decode("euc_jp", errors="ignore")
            soup = BeautifulSoup(html_text, "html.parser")

            result_ul = soup.find("ul", class_="display")
            if not result_ul:
                return []

            # --- 解析逻辑不变 ---
            items = []
            for li in result_ul.find_all("li"):
                block = li.select_one("#detail_block")
                if not block:
                    continue

                title_tag = block.select_one("a.blueb[href*='soft.phtml?id=']")
                if not title_tag:
                    continue

                item_type = (block.select_one("span.orangeb") or {}).get_text(strip=True) or "未知"

                price_text = (block.select_one(".redb") or {}).get_text(strip=True)
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
            resp = await self.client.get(url, timeout=15)
            resp.raise_for_status()
            html_text = resp.content.decode("euc_jp", errors="ignore")
            soup = BeautifulSoup(html_text, "html.parser")

            if "年齢認証" in soup.title.text:
                logger.error("[Getchu] 绕过年龄验证失败，页面内容不正确。")
                return {}

            info_table = soup.find("table", id="soft_table")

            # --- 解析逻辑不变 ---
            def extract_info(keyword):
                if not info_table:
                    return None
                header = info_table.find("td", class_="right", string=re.compile(keyword))
                if header and header.find_next_sibling("td"):
                    return header.find_next_sibling("td").get_text("、", strip=True)
                return None

            cover_a = soup.select_one("a.highslide[href*='/graphics/']")
            raw_image_url = (
                urljoin(self.BASE_URL, cover_a["href"]) if cover_a and cover_a.img else None
            )
            image_url = (
                raw_image_url.replace("https://www.getchu.com", "https://cover.ydgal.com")
                if raw_image_url
                else None
            )

            brand, brand_site = None, None
            brand_header = soup.find("td", class_="right", string=re.compile("ブランド"))
            if brand_header and brand_header.find_next_sibling("td"):
                brand_td = brand_header.find_next_sibling("td")
                a_tag = brand_td.find("a")
                if a_tag:
                    brand = a_tag.get_text(strip=True)
                    brand_site = a_tag.get("href")

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
                "发售日": extract_info("発売日"),
                "价格": extract_info("定価"),
                "原画": extract_info("原画"),
                "剧本": extract_info("シナリオ"),
            }
        except Exception as e:
            logger.error(f"[Getchu] (httpx)抓取详情失败: {e}")
            return {}
