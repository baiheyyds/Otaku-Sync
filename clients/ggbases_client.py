# clients/ggbases_client.py
import asyncio
import os
import urllib.parse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from utils import logger
from utils.tag_logger import append_new_tags
from .base_client import BaseClient

TAG_GGBASE_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_ggbase.json")


class GGBasesClient(BaseClient):
    def __init__(self, client):
        super().__init__(client, base_url="https://www.ggbases.com/")
        self.driver = None
        self.selenium_timeout = 5

    def set_driver(self, driver):
        self.driver = driver
        stealth(
            self.driver,
            languages=["zh-CN", "zh"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    async def choose_or_parse_popular_url_with_requests(self, keyword: str) -> list:
        logger.info(f"[GGBases] 正在搜索: {keyword}")
        try:
            encoded = urllib.parse.quote(keyword)
            search_url = f"/search.so?p=0&title={encoded}&advanced="
            resp = await self.get(search_url, timeout=15)
            if not resp:
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.find_all("tr", class_="dtr")
            candidates = []

            for row in rows[:15]:
                detail_link = row.find("a", href=lambda x: x and "/view.so?id=" in x)
                if not detail_link:
                    continue

                url = urllib.parse.urljoin(self.base_url, detail_link["href"])
                all_tds = row.find_all("td")
                title = (
                    all_tds[1].get_text(separator=" ", strip=True) if len(all_tds) > 1 else "无标题"
                )

                popularity = 0
                pop_a = row.select_one("a.l-a span")
                if pop_a and pop_a.get_text(strip=True).isdigit():
                    popularity = int(pop_a.get_text(strip=True))

                size = None
                if len(all_tds) > 2:
                    size_text = all_tds[2].get_text(strip=True)
                    if size_text and size_text[-1].upper() in "BKMGT":
                        size = size_text

                candidates.append(
                    {
                        "title": title,
                        "url": url,
                        "popularity": popularity,
                        "容量": size,
                    }
                )

            if not candidates:
                logger.warn("[GGBases] 未找到任何结果")
                return []

            logger.success(f"[GGBases] 搜索到 {len(candidates)} 个候选结果")
            return candidates

        except Exception as e:
            logger.error(f"[GGBases] 解析搜索结果失败: {e}")
            return []

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

    def _normalize_url(self, src):
        if not src or src.startswith("data:"):
            return None
        if src.startswith("//"):
            return "https" + src
        if src.startswith("/"):
            return urllib.parse.urljoin(self.base_url, src)
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
