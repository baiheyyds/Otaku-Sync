# clients/dlsite_client.py
# 该模块用于与 Dlsite 网站交互，获取游戏信息和品牌数据
import os
import urllib.parse

import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.tag_logger import append_new_tags

TAG_JP_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_jp_to_cn.json")


class DlsiteClient:
    BASE_URL = "https://www.dlsite.com"

    def __init__(self, headers=None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.dlsite.com/maniax/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.driver = None

    def set_driver(self, driver):
        """外部注入driver的方法"""
        self.driver = driver

    def search(self, keyword, limit=30):
        print(f"🔍 [Dlsite] 正在搜索关键词: {keyword}")
        query = urllib.parse.quote_plus(keyword)
        url = (
            f"{self.BASE_URL}/maniax/fsr/=/language/jp/"
            f"sex_category%5B0%5D/male/"
            f"keyword/{query}/"
            f"work_category%5B0%5D/doujin/"
            f"work_category%5B1%5D/books/"
            f"work_category%5B2%5D/pc/"
            f"work_category%5B3%5D/app/"
            f"order%5B0%5D/trend/"
            f"options_and_or/and/"
            f"per_page/30/"
            f"page/1/"
            f"from/fs.header"
        )
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        seen = set()

        for a in soup.select("a[href*='/work/=/product_id/']"):
            container = a.find_parent()
            for _ in range(3):
                if container is None:
                    break
                price_tag = container.select_one(".price, .work_price, .price_display")
                if price_tag:
                    break
                container = container.parent
            price = price_tag.get_text(strip=True) if price_tag else "无"
            title = a.get("title", "").strip()
            href = a["href"]
            full_url = href if href.startswith("http") else self.BASE_URL + href
            li_tag = a.find_parent("li", class_="search_result_img_box_inner")
            work_type_tag = li_tag.select_one(".work_category a") if li_tag else None
            work_type = work_type_tag.get_text(strip=True) if work_type_tag else None

            if title and full_url and full_url not in seen:
                results.append({"title": title, "url": full_url, "price": price, "类型": work_type})
                seen.add(full_url)
            if len(results) >= limit:
                break

        exclude_keywords = ["単行本", "マンガ", "小説", "書籍", "雑誌/アンソロ", "ボイス・ASMR", "音楽", "動画"]
        filtered_results = [
            item for item in results if not any(ex_kw in item.get("类型", "") for ex_kw in exclude_keywords)
        ]

        print(f"✅ [Dlsite] 筛选后找到 {len(filtered_results)} 条游戏相关结果")
        return filtered_results

    def get_game_detail(self, url):
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        brand_tag = soup.select_one("#work_maker .maker_name a")
        brand = brand_tag.get_text(strip=True) if brand_tag else None
        brand_page_url = brand_tag["href"] if brand_tag and brand_tag.has_attr("href") else None
        if brand_page_url and not brand_page_url.startswith("http"):
            brand_page_url = self.BASE_URL + brand_page_url

        sale_date, scenario, illustrator, voice_actor, music, genres, work_type, capacity = (
            None,
            [],
            [],
            [],
            [],
            [],
            [],
            None,
        )
        table = soup.find("table", id="work_outline")
        if table:
            for tr in table.find_all("tr"):
                th, td = tr.find("th"), tr.find("td")
                if not th or not td:
                    continue
                key = th.get_text(strip=True)
                if key == "販売日":
                    sale_date = td.get_text(strip=True)
                elif key == "シナリオ":
                    scenario = [a.get_text(strip=True) for a in td.find_all("a")]
                elif key == "イラスト":
                    illustrator = [a.get_text(strip=True) for a in td.find_all("a")]
                elif key == "声優":
                    voice_actor = [a.get_text(strip=True) for a in td.find_all("a")]
                elif key == "音楽":
                    music = [a.get_text(strip=True) for a in td.find_all("a")]
                elif key == "ジャンル":
                    genres = [a.get_text(strip=True) for a in td.find_all("a")]
                elif key == "作品形式":
                    spans = td.find_all("span", title=True)
                    mapping = {
                        "ロールプレイング": "RPG",
                        "アドベンチャー": "ADV",
                        "シミュレーション": "模拟",
                        "アクション": "ACT",
                        "音声あり": "有声音",
                        "音楽あり": "有音乐",
                        "動画あり": "有动画",
                    }
                    work_type = [mapping.get(s["title"].strip(), s["title"].strip()) for s in spans]
                elif key == "ファイル容量":
                    raw_text = td.get_text(strip=True)
                    capacity = raw_text.replace("総計", "").strip()

        cover = soup.find("meta", property="og:image")["content"] if soup.find("meta", property="og:image") else None
        if genres:
            append_new_tags(TAG_JP_PATH, genres)

        return {
            "品牌": brand,
            "发售日": sale_date,
            "剧本": scenario,
            "原画": illustrator,
            "声优": voice_actor,
            "音乐": music,
            "标签": genres,
            "作品形式": work_type,
            "封面图链接": cover,
            "品牌页链接": brand_page_url,
            "容量": capacity,
        }

    def get_brand_extra_info_with_selenium(self, brand_page_url):
        print(f"🔩 [Dlsite] 正在启动Selenium抓取品牌额外信息...")
        if not self.driver:
            raise RuntimeError("DlsiteClient的Selenium driver未设置，无法执行JS渲染抓取。")
        if not brand_page_url:
            return {"官网": None, "图标": None}
        try:
            self.driver.get(brand_page_url)
            wait = WebDriverWait(self.driver, 10)
            link_block_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.link_cien")))
            soup = BeautifulSoup(link_block_element.get_attribute("outerHTML"), "html.parser")
            cien_link = soup.select_one("a[href]")
            icon_img = soup.select_one("img[src]")
            official_url = cien_link["href"].strip() if cien_link else None
            icon_url = icon_img["src"].strip() if icon_img else None
            print(f"✅ [Dlsite] (Selenium)获取成功: 官网={official_url}, 图标={icon_url}")
            return {"官网": official_url, "图标": icon_url}
        except Exception as e:
            print(f"❌ [Dlsite] (Selenium)抓取品牌信息失败 {brand_page_url}: {e}")
            return {"官网": None, "图标": None}
