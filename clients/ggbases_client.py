# clients/ggbases_client.py
# 该模块用于与 GGBases 网站交互，获取游戏信息和标签
import contextlib
import os
import sys
import time
import urllib.parse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.tag_logger import append_new_tags
from utils.tag_mapping import map_and_translate_tags

TAG_GGBASE_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_ggbase.json")


@contextlib.contextmanager
def suppress_stdout_stderr():
    """重定向stdout和stderr到null，屏蔽浏览器启动时日志。"""
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


def create_silent_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.page_load_strategy = "eager"

    log_path = "NUL" if os.name == "nt" else "/dev/null"
    service = Service(log_path=log_path)

    with suppress_stdout_stderr():
        driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1200, 800)
    return driver


class GGBasesClient:
    BASE_URL = "https://www.ggbases.com"

    def __init__(self, driver=None):
        self.driver = driver or create_silent_chrome_driver()
        self.external_driver = driver is not None
        self._cache = {}

    def close(self):
        if not self.external_driver and self.driver:
            self.driver.quit()

    def __del__(self):
        self.close()

    def safe_get(self, url, wait_selector=None, timeout=8):
        try:
            self.driver.set_page_load_timeout(timeout)
            self.driver.get(url)
            if wait_selector:
                WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(wait_selector))
            time.sleep(1.5)
            return self.driver.page_source
        except Exception as e:
            print(f"⚠️ 页面加载失败: {url} | 错误: {e}")
            try:
                return self.driver.execute_script("return document.documentElement.outerHTML")
            except:
                return ""

    def get_search_page_html(self, keyword):
        encoded = urllib.parse.quote(keyword)
        url = f"{self.BASE_URL}/search.so?p=0&title={encoded}&advanced="
        return self.safe_get(url, wait_selector=(By.CSS_SELECTOR, "tr.dtr"))

    def get_info_by_url(self, detail_url):
        if not detail_url:
            return {}

        try:
            detail_html = self.safe_get(detail_url, wait_selector=(By.TAG_NAME, "tr"))
            soup = BeautifulSoup(detail_html, "lxml")
            info = {
                "容量": self._extract_game_size(soup),
                "封面图链接": self._extract_cover_url(soup),
                "标签": self._extract_tags(soup),
            }
            return info
        except Exception as e:
            print(f"⚠️ 抓取 GGBases 详情页失败: {e}")
            return {}

    def choose_or_parse_popular_url(self, html=None, interactive=False, search_url=None):
        if html is None:
            if not search_url:
                print("❌ 需要传入 search_url 或 html")
                return None
            try:
                self.driver.get(search_url)
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "tr.dtr")))
                time.sleep(1.5)
                html = self.driver.page_source
            except Exception as e:
                print(f"⚠️ 页面加载失败或无搜索结果: {e}")
                return None

        soup = BeautifulSoup(html, "lxml")
        rows = soup.find_all("tr", class_="dtr")
        candidates = []

        for i, row in enumerate(rows[:10]):
            detail_link = row.find("a", href=lambda x: x and "/view.so?id=" in x)
            if not detail_link:
                continue
            url = urllib.parse.urljoin(self.BASE_URL, detail_link["href"])

            title = "无标题"
            try:
                title_td = row.find_all("td")[1]
                if title_td:
                    title = title_td.get_text(separator=" ", strip=True)
            except Exception as e:
                print(f"⚠️ 标题提取失败: {e}")

            popularity = 0
            try:
                pop_a = row.select_one("a.l-a")
                if pop_a:
                    pop_span = pop_a.find("span")
                    if pop_span:
                        pop_text = pop_span.get_text(strip=True)
                        if pop_text.isdigit():
                            popularity = int(pop_text)
            except Exception as e:
                print(f"⚠️ 热度提取异常: {e}")

            candidates.append({"title": title, "url": url, "popularity": popularity})

        if not candidates:
            print("⚠️ GGBases 没有找到有效结果")
            return None
        if not interactive:
            print(f"🔎 共找到 {len(candidates)} 个结果，自动选择热度最高的项。")

        best = max(candidates, key=lambda x: x["popularity"])
        print(f"🔥 自动选择热度最高结果: {best['title']}（热度: {best['popularity']}） | 链接: {best['url']}")

        if not interactive or len(candidates) == 1:
            return best["url"]

        print("\n🎯 GGBases 检测到多个可能作品，请手动选择：")
        for i, c in enumerate(candidates):
            print(f"[{i}] 🎮 {c['title']}（热度: {c['popularity']}） | 🔗 {c['url']}")

        try:
            choice = input("👉 请输入编号（默认0）或直接回车：").strip()
            selected_index = int(choice) if choice else 0
            if not (0 <= selected_index < len(candidates)):
                print("⚠️ 编号超出范围，默认使用第一个结果")
                selected_index = 0
        except Exception as e:
            print(f"⚠️ 输入异常，默认使用第一个结果: {e}")
            selected_index = 0

        selected = candidates[selected_index]
        print(f"✅ 你选择了 [{selected_index}] {selected['title']}，链接为: {selected['url']}")
        return selected["url"]

    def _normalize_url(self, src):
        if not src or src.startswith("data:"):
            return None
        if src.startswith("//"):
            return "https:" + src
        elif src.startswith("/"):
            return urllib.parse.urljoin(self.BASE_URL, src)
        return src

    def get_all_info_by_title(self, title, verbose=False, interactive=False):
        if title in self._cache:
            return self._cache[title]

        try:
            encoded = urllib.parse.quote(title)
            search_url = f"{self.BASE_URL}/search.so?p=0&title={encoded}&advanced="
            detail_url = self.choose_or_parse_popular_url(html=None, interactive=interactive, search_url=search_url)
            if not detail_url:
                self._cache[title] = {}
                return {}

            info = self.get_info_by_url(detail_url)
            self._cache[title] = info
            return info
        except Exception as e:
            print(f"⚠️ 获取 GGBases 信息失败: {e}")
            self._cache[title] = {}
            return {}

    def _extract_game_size(self, soup):
        size_td = soup.select_one('td:-soup-contains("大小"), td:-soup-contains("容量")')
        if size_td:
            span = size_td.find("span", class_="label")
            if span:
                return span.get_text(strip=True)
        return None

    def _extract_cover_url(self, soup):
        img = soup.select_one("div[markdown-text] img, #img00")
        if img and img.get("src"):
            return self._normalize_url(img["src"])
        a_tag = soup.select_one("div[markdown-text] a[href]")
        if a_tag:
            return self._normalize_url(a_tag["href"])
        try:
            img = WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.ID, "img00")))
            return self._normalize_url(img.get_attribute("src"))
        except:
            return None

    def _extract_tags(self, soup):
        female_tags = [
            span.get_text(strip=True)
            for tr in soup.find_all("tr")
            if tr.find("a", href=lambda x: x and "tags.so?target=female" in x)
            for span in tr.find_all("span", class_="female_span")
        ]
        # 不抓取dlsite标签，dlsite标签单独处理
        all_tags = female_tags
        if all_tags:
            append_new_tags(TAG_GGBASE_PATH, all_tags)
        return all_tags

    def get_game_size_by_title(self, title):
        return self.get_all_info_by_title(title).get("容量")

    def get_game_cover_by_title(self, title):
        return self.get_all_info_by_title(title).get("封面图链接")

    def try_supplement_tags_via_ggbases(self, search_keyword, notion_client, notion_title):
        try:
            info = self.get_all_info_by_title(search_keyword)
            tags = info.get("标签", [])
            mapped_tags = map_and_translate_tags(tags, source="ggbase")
            if not mapped_tags:
                print("❌ 未找到标签")
                return
            page = notion_client.search_game(notion_title)
            if not page:
                print("❌ 没有对应 Notion 条目")
                return
            page_id = page[0]["id"]
            patch_payload = {"properties": {"标签": {"multi_select": [{"name": t} for t in mapped_tags]}}}
            url = f"https://api.notion.com/v1/pages/{page_id}"
            if notion_client._request("PATCH", url, patch_payload):
                print(f"🏷️ 标签已补全: {' '.join(mapped_tags)}")
            else:
                print("❌ 标签补全失败")
        except Exception as e:
            print(f"❌ 标签补全异常: {e}")
        except Exception as e:
            print(f"❌ 标签补全异常: {e}")
