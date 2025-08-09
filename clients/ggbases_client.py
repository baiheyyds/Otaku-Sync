# clients/ggbases_client.py
import asyncio
import os
import urllib.parse

import httpx
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from utils import logger
from utils.tag_logger import append_new_tags

TAG_GGBASE_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_ggbase.json")


class GGBasesClient:
    BASE_URL = "https://ggbases.dlgal.com"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.client.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            }
        )
        self.driver = None  # 将持有专属的 driver
        self.selenium_timeout = 5

    def set_driver(self, driver):
        """外部注入专属的driver实例"""
        self.driver = driver
        # 对专属 driver 进行一次性伪装
        stealth(
            self.driver,
            languages=["zh-CN", "zh"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    # ... choose_or_parse_popular_url_with_requests 方法无变化 ...
    async def choose_or_parse_popular_url_with_requests(self, keyword):
        logger.info(f"[GGBases] 正在通过 requests 搜索: {keyword}")
        try:
            encoded = urllib.parse.quote(keyword)
            search_url = f"{self.BASE_URL}/search.so?p=0&title={encoded}&advanced="
            resp = await self.client.get(search_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.find_all("tr", class_="dtr")
            candidates = []
            for row in rows[:10]:
                detail_link = row.find("a", href=lambda x: x and "/view.so?id=" in x)
                if not detail_link:
                    continue
                url = urllib.parse.urljoin(self.BASE_URL, detail_link["href"])
                title = (
                    row.find_all("td")[1].get_text(separator=" ", strip=True)
                    if len(row.find_all("td")) > 1
                    else "无标题"
                )
                popularity = 0
                pop_a = row.select_one("a.l-a span")
                if pop_a and pop_a.get_text(strip=True).isdigit():
                    popularity = int(pop_a.get_text(strip=True))
                candidates.append({"title": title, "url": url, "popularity": popularity})
            if not candidates:
                logger.warn("[GGBases] (requests) 没有找到有效结果")
                return None
            best = max(candidates, key=lambda x: x["popularity"])
            logger.success(
                f"[GGBases] (requests) 自动选择热度最高结果: {best['title']} ({best['popularity']})"
            )
            return best["url"]
        except httpx.RequestError as e:
            logger.error(f"[GGBases] (requests) 搜索请求失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[GGBases] (requests) 解析搜索结果失败: {e}")
            return None

    async def get_info_by_url_with_selenium(self, detail_url):
        if not self.driver:
            raise RuntimeError("GGBasesClient的专属driver未设置。")
        if not detail_url:
            return {}
        logger.info(f"[GGBases] 正在用Selenium抓取详情页: {detail_url}")

        def _blocking_task():
            try:
                self.driver.get(detail_url)
                wait = WebDriverWait(self.driver, self.selenium_timeout)
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'a[href*="tags.so?target=female"]')
                    )
                )
                soup = BeautifulSoup(self.driver.page_source, "lxml")
                info = {
                    "容量": self._extract_game_size(soup),
                    "封面图链接": self._extract_cover_url(soup),
                    "标签": self._extract_tags(soup),
                }
                logger.success("[GGBases] (Selenium) 详情页信息抓取成功")
                return info
            except Exception as e:
                logger.warn(f"[GGBases] (Selenium) 抓取详情页失败: {e}")
                return {}

        return await asyncio.to_thread(_blocking_task)

    # ... _normalize_url, _extract_game_size, _extract_cover_url, _extract_tags 方法无变化 ...
    def _normalize_url(self, src):
        if not src or src.startswith("data:"):
            return None
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            return urllib.parse.urljoin(self.BASE_URL, src)
        return src

    def _extract_game_size(self, soup):
        size_td = soup.select_one('td:-soup-contains("大小"), td:-soup-contains("容量")')
        if size_td and (span := size_td.find("span", class_="label")):
            return span.get_text(strip=True)
        return None

    def _extract_cover_url(self, soup):
        img = soup.select_one("div[markdown-text] img, #img00")
        if img and img.get("src"):
            return self._normalize_url(img["src"])
        a_tag = soup.select_one("div[markdown-text] a[href]")
        if a_tag:
            return self._normalize_url(a_tag["href"])
        return None

    def _extract_tags(self, soup):
        female_tags = [
            span.get_text(strip=True)
            for tr in soup.find_all("tr")
            if tr.find("a", href=lambda x: x and "tags.so?target=female" in x)
            for span in tr.find_all("span", class_="female_span")
        ]
        if female_tags:
            append_new_tags(TAG_GGBASE_PATH, female_tags)
        return female_tags
