# clients/dlsite_client.py
import asyncio
import logging
import os
import traceback
import urllib.parse

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from utils.tag_logger import append_new_tags

from .base_client import BaseClient

TAG_JP_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_jp_to_cn.json")


class DlsiteClient(BaseClient):
    def __init__(self, client):
        super().__init__(client, base_url="https://www.dlsite.com")
        self.headers.update({
            "Referer": "https://www.dlsite.com/maniax/",
        })
        self.driver = None
        self.selenium_timeout = 5

    def set_driver(self, driver):
        self.driver = driver
        stealth(
            self.driver,
            languages=["ja-JP", "ja"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    def has_driver(self):
        """检查是否已设置驱动程序。"""
        return self.driver is not None

    async def search(self, keyword, limit=30):
        logging.info(f"🔍 [Dlsite] 正在搜索关键词: {keyword}")
        query = urllib.parse.quote_plus(keyword)
        url = f"/maniax/fsr/=/language/jp/sex_category%5B0%5D/male/keyword/{query}/work_category%5B0%5D/doujin/work_category%5B1%5D/books/work_category%5B2%5D/pc/work_category%5B3%5D/app/order%5B0%5D/trend/options_and_or/and/per_page/30/page/1/from/fs.header"

        resp = await self.get(url, timeout=15)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        seen = set()

        for li in soup.select("li.search_result_img_box_inner"):
            if len(results) >= limit:
                break

            title_a = li.select_one(".work_name a")
            if not title_a:
                continue

            href = title_a.get("href")
            if not href:
                continue
            
            full_url = href if href.startswith("http") else self.base_url + href
            if full_url in seen:
                continue
            
            title = title_a.get("title", "").strip()
            if not title:
                continue

            price_tag = li.select_one(".work_price, .price_display")
            price = price_tag.get_text(strip=True) if price_tag else "无"

            work_type_tag = li.select_one(".work_category a")
            work_type = work_type_tag.get_text(strip=True) if work_type_tag else None

            thumbnail_url = None
            img_tag = li.select_one("img.lazy")
            if img_tag:
                thumbnail_url = img_tag.get('data-src') or img_tag.get('src')

            results.append({
                "title": title,
                "url": full_url,
                "price": price,
                "类型": work_type,
                "thumbnail_url": thumbnail_url
            })
            seen.add(full_url)

        exclude_keywords = [
            "単行本", "マンガ", "小説", "書籍", "雑誌/アンソロ",
            "ボイス・ASMR", "音楽", "動画", "CG・イラスト", "単話",
        ]
        filtered_results = [
            item
            for item in results
            if not any(ex_kw in (item.get("类型") or "") for ex_kw in exclude_keywords)
        ]
        logging.info(f"✅ [Dlsite] 筛选后找到 {len(filtered_results)} 条游戏相关结果")
        return filtered_results

    async def get_game_detail(self, url):
        resp = await self.get(url, timeout=15, headers={"Cookie": "adultchecked=1;"})
        if not resp:
            return {}
        try:
            soup = BeautifulSoup(resp.text, "lxml")
            brand_tag = soup.select_one("#work_maker .maker_name a")
            brand = brand_tag.get_text(strip=True) if brand_tag else None
            brand_page_url = brand_tag["href"] if brand_tag and brand_tag.has_attr("href") else None
            if brand_page_url and not brand_page_url.startswith("http"):
                brand_page_url = self.base_url + brand_page_url

            details = {}

            table = soup.find("table", id="work_outline")
            if table:
                for tr in table.find_all("tr"):
                    th, td = tr.find("th"), tr.find("td")
                    if not th or not td:
                        continue
                    key = th.get_text(strip=True)

                    def extract_list_from_td(table_cell):
                        # Replace <br> tags with a common separator
                        for br in table_cell.find_all("br"):
                            br.replace_with(",")

                        # Get all text, using the common separator
                        all_text = table_cell.get_text(separator=",")

                        # Standardize all separators to the common one and then split
                        processed_text = all_text.replace('、', ',').replace('/', ',').replace('，', ',')
                        return [name.strip() for name in processed_text.split(',') if name.strip()]

                    if key in self.STAFF_MAPPING:
                        details[self.STAFF_MAPPING[key]] = extract_list_from_td(td)
                    elif key == "販売日":
                        details["发售日"] = td.get_text(strip=True)
                    elif key == "ジャンル":
                        details["标签"] = [a.get_text(strip=True) for a in td.find_all("a")]
                    elif key == "作品形式":
                        spans = td.find_all("span", title=True)
                        details["作品形式"] = [
                            self._genre_reverse_mapping.get(s["title"].strip().upper(), s["title"].strip())
                            for s in spans
                            if s.has_attr("title")
                        ]
                    elif key == "ファイル容量":
                        value_container = td.select_one(".main_genre") or td
                        details["容量"] = (
                            value_container.get_text(strip=True).replace("总计", "").strip()
                        )

            cover_tag = soup.find("meta", property="og:image")
            if cover_tag:
                details["封面图链接"] = cover_tag["content"]
            if details.get("标签"):
                append_new_tags(TAG_JP_PATH, details["标签"])

            return {
                "品牌": brand,
                "发售日": details.get("发售日"),
                "剧本": details.get("剧本", []),
                "原画": details.get("原画", []),
                "声优": details.get("声优", []),
                "音乐": details.get("音乐", []),
                "标签": details.get("标签", []),
                "作品形式": details.get("作品形式", []),
                "封面图链接": details.get("封面图链接"),
                "品牌页链接": brand_page_url,
                "容量": details.get("容量"),
            }
        except Exception as e:
            logging.error(f"❌ [Dlsite] 解析详情页失败: {url} - {e}")
            traceback.print_exc()
            return {}

    async def get_brand_extra_info_with_selenium(self, brand_page_url):
        logging.info("🔍 [Dlsite] 正在用Selenium抓取品牌额外信息...")
        if not self.driver:
            raise RuntimeError("DlsiteClient的专属driver未设置。")
        if not brand_page_url:
            return {}

        def _blocking_task():
            try:
                self.driver.get(brand_page_url)
                try:
                    # 尝试自动通过年龄验证，设置较短的等待时间
                    age_check_wait = WebDriverWait(self.driver, 3)
                    yes_button = age_check_wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_yes a"))
                    )
                    yes_button.click()
                    logging.info("🔍 [Dlsite] (Selenium) 已自动通过年龄验证。")
                except Exception:
                    pass # 年龄验证不是每次都有，忽略失败

                # 主要内容等待
                wait = WebDriverWait(self.driver, self.selenium_timeout)
                cien_url = None
                icon_url = None

                try:
                    # 策略1: 直接、独立地等待每个目标元素加载完成
                    cien_link_element = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='ci-en.dlsite.com']"))
                    )
                    cien_url = cien_link_element.get_attribute("href").strip()
                except TimeoutException:
                    logging.warning("⚠️ [Dlsite] (Selenium) 在品牌页面未找到 Ci-en 链接。")

                try:
                    icon_img_element = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".creator_icon img[src]"))
                    )
                    icon_url = icon_img_element.get_attribute("src").strip()
                except TimeoutException:
                    logging.warning("⚠️ [Dlsite] (Selenium) 在品牌页面未找到图标。")

                if cien_url or icon_url:
                    logging.info(
                        f"✅ [Dlsite] (Selenium) 获取成功: Ci-en={cien_url}, 图标={icon_url}"
                    )
                return {"ci_en_url": cien_url, "icon_url": icon_url}

            except Exception as e:
                logging.error(
                    f"❌ [Dlsite] (Selenium) 抓取品牌信息时发生未知错误 {brand_page_url}: {e}"
                )
                return {}

        return await asyncio.to_thread(_blocking_task)
