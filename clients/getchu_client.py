# clients/getchu_client.py
# GetchuClient 类用于抓取 Getchu 网站的游戏信息
import random
import re
import time
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class GetchuClient:
    BASE_URL = "https://www.getchu.com"
    SEARCH_URL = "https://www.getchu.com/php/nsearch.phtml"

    def __init__(self, driver=None, driver_path=None, headless=True):
        self.driver = driver
        self.headless = headless
        self.driver_path = driver_path
        self.session = requests.Session()

        if not self.driver:
            self._init_driver()

    def _init_driver(self):
        if self.driver is not None:
            return
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--log-level=3")
        service = ChromeService(executable_path=self.driver_path) if self.driver_path else ChromeService()
        self.driver = webdriver.Chrome(service=service, options=options)

    def _get_headers(self):
        headers = {
            "User-Agent": random.choice(
                [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/91.0.864.67 Safari/537.36",
                ]
            ),
            "Referer": "https://www.getchu.com/",
        }
        return headers

    def search(self, keyword):
        print("🔍 [Getchu] 开始搜索...")
        try:
            safe_keyword = keyword.replace("～", "〜")
            encoded_keyword = quote(safe_keyword.encode("shift_jis"))
            url = f"{self.SEARCH_URL}?genre=all&search_keyword={encoded_keyword}&check_key_dtl=1&submit="
            retries = 5
            while retries > 0:
                resp = self.session.get(url, timeout=10, headers=self._get_headers())
                if resp.status_code == 403:
                    retries -= 1
                    print(f"❌ 请求失败，剩余重试次数: {retries}")
                    time.sleep(2)
                else:
                    break

            if resp.status_code != 200:
                print(f"❌ 搜索失败，状态码: {resp.status_code}")
                return []

            resp.encoding = "euc_jp"
            soup = BeautifulSoup(resp.text, "html.parser")
            result_ul = soup.find("ul", class_="display")
            if not result_ul:
                print("⚠️ 未找到搜索结果区域。")
                return []

            items = []
            for li in result_ul.find_all("li"):
                block = li.select_one("#detail_block")
                if not block:
                    continue

                title_tag = block.select_one("a.blueb[href*='soft.phtml?id=']")

                # 提取类型
                type_tag = block.select_one("span.orangeb")
                item_type = type_tag.get_text(strip=True) if type_tag else "未知"

                # 🛠️ 增强版价格提取逻辑
                price_tag = block.select_one(".redb")
                if price_tag:
                    price = price_tag.get_text(strip=True)
                else:
                    price = "未知"
                    for p in block.find_all("p"):
                        text = p.get_text()
                        if "定価" in text:
                            match = re.search(r"定価[:：]?\s*([^\s<（]+)", text)
                            if match:
                                price = match.group(1)
                                break

                if title_tag:
                    game_id = re.search(r"id=(\d+)", title_tag["href"])
                    if not game_id:
                        continue
                    items.append(
                        {
                            "title": title_tag.get_text(strip=True),
                            "url": f"{self.BASE_URL}/soft.phtml?id={game_id.group(1)}",
                            "价格": price,
                            "类型": item_type,  # ✅ 新增字段
                        }
                    )

            # 新增：过滤只保留游戏类型
            items = [item for item in items if "ゲーム" in item.get("类型", "")]

            exclude_keywords = ["グッズ", "BOOKS", "CD", "音楽"]
            items = [item for item in items if not any(ex_kw in item.get("类型", "") for ex_kw in exclude_keywords)]

            print(f"✅ 找到 {len(items)} 个搜索结果。")
            return items

        except UnicodeEncodeError as ue:
            print(f"❌ 编码失败：{ue}")
            return []
        except Exception as e:
            print(f"❌ 搜索失败：{e}")
            return []

    def get_game_detail(self, url):
        try:
            print(f"\n🚀 正在加载游戏详情页: {url}")
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            if "年齢認証" in self.driver.title:
                print("⚠️ 遇到年龄验证，尝试通过...")
                links = self.driver.find_elements(By.TAG_NAME, "a")
                for link in links:
                    if "すすむ" in link.text:
                        link.click()
                        WebDriverWait(self.driver, 10).until(EC.title_contains("Getchu"))
                        break

            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            info_table = soup.find("table", {"width": "100%", "style": "padding:1px;"})

            def extract_info(keyword):
                if not info_table:
                    return None
                for tr in info_table.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) >= 2 and keyword in tds[0].get_text(strip=True):
                        return tds[1].get_text("、", strip=True)
                return None

            img_tag = soup.select_one("a.highslide > img")
            raw_image_url = urljoin(self.BASE_URL, img_tag["src"]) if img_tag and img_tag.get("src") else None
            image_url = raw_image_url.replace(self.BASE_URL, "https://cover.ydgal.com") if raw_image_url else None

            # --- 新结构的品牌信息提取 ---
            brand, brand_site = None, None
            trs = soup.find_all("tr")
            for tr in trs:
                tds = tr.find_all("td")
                if len(tds) >= 2 and "ブランド" in tds[0].get_text(strip=True):
                    a_tags = tds[1].find_all("a")
                    if a_tags:
                        brand = a_tags[0].get_text(strip=True)
                        brand_site = a_tags[0]["href"]
                    break

            title_tag = soup.select_one("title")
            title = title_tag.text.strip().split(" (")[0] if title_tag else None

            print("📦 正在提取字段...")

            result = {
                "封面图链接": image_url,
                "标题": title,
                "品牌": brand,
                "品牌官网": brand_site,
                "发售日": extract_info("発売日"),
                "价格": extract_info("定価"),
                "原画": extract_info("原画"),
                "剧本": extract_info("シナリオ"),
            }

            print("\n🎯 抓取结果:")
            for k, v in result.items():
                print(f"{k}: {v}")

            return result

        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            return {}

    def close(self):
        if self.driver:
            print("🧹 正在关闭浏览器驱动...")
            self.driver.quit()
            self.driver = None


if __name__ == "__main__":
    client = GetchuClient(headless=True)
    try:
        while True:
            keyword = input("\n请输入游戏关键词（日文，回车退出）：").strip()
            if not keyword:
                break
            results = client.search(keyword)
            if not results:
                print("没有搜索结果。")
                continue
            for i, item in enumerate(results):
                print(f"[{i}] 🎮 {item['title']} | 💴 {item['价格']}")
            idx = input("请选择游戏编号查看详情（回车跳过）：").strip()
            if idx.isdigit() and 0 <= int(idx) < len(results):
                client.get_game_detail(results[int(idx)]["url"])
    finally:
        client.close()
        client.close()
