# clients/dlsite_client.py
# 该模块用于与 Dlsite 网站交互，获取游戏信息和品牌数据
import contextlib
import os
import re
import sys
import urllib.parse

import requests
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.tag_logger import append_new_tags

TAG_JP_PATH = os.path.join(os.path.dirname(__file__), "..", "mapping", "tag_jp_to_cn.json")


@contextlib.contextmanager
def suppress_stdout_stderr():
    """
    重定向stdout和stderr到null，屏蔽浏览器启动时日志。
    """
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


def create_silent_uc_driver():
    # 降低tensorflow、CUDA等库的日志
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    options = uc.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--window-size=1280,1024")

    # Chrome日志级别参数
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])

    with suppress_stdout_stderr():
        driver = uc.Chrome(options=options)
    return driver


class DlsiteClient:
    BASE_URL = "https://www.dlsite.com"

    def __init__(self, headers=None, driver=None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.dlsite.com/maniax/",
        }
        self.driver = driver
        self.external_driver = driver is not None
        self.session = requests.Session()
        self.session.headers.update(self.headers)

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
            for _ in range(3):  # 向上找 price 容器
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

            # 查找作品类型（如：動画、CG・イラスト等）
            li_tag = a.find_parent("li", class_="search_result_img_box_inner")
            work_type_tag = li_tag.select_one(".work_category a") if li_tag else None
            work_type = work_type_tag.get_text(strip=True) if work_type_tag else None

            if title and full_url and full_url not in seen:
                results.append(
                    {
                        "title": title,
                        "url": full_url,
                        "price": price,
                        "类型": work_type,  # ✅ 新增字段
                    }
                )
                seen.add(full_url)

            if len(results) >= limit:
                break

        # === 只排除非游戏类别，保留其余 ===
        exclude_keywords = ["単行本", "マンガ", "小説", "書籍", "雑誌/アンソロ", "ボイス・ASMR", "音楽", "動画"]

        filtered_results = []
        for item in results:
            item_type = item.get("类型", "")
            if not any(ex_kw in item_type for ex_kw in exclude_keywords):
                filtered_results.append(item)

        print(f"✅ [Dlsite] 筛选后找到 {len(filtered_results)} 条游戏相关结果")
        return filtered_results

    def get_game_detail(self, url):
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 品牌名称及链接
        brand_tag = soup.select_one("#work_maker .maker_name a")
        brand = brand_tag.get_text(strip=True) if brand_tag else None
        brand_page_url = brand_tag["href"] if brand_tag and brand_tag.has_attr("href") else None
        if brand_page_url and not brand_page_url.startswith("http"):
            brand_page_url = self.BASE_URL + brand_page_url

        # 额外信息初始化
        sale_date = None
        scenario = []
        illustrator = []
        voice_actor = []
        music = []
        genres = []
        work_type = []

        # 解析信息表
        table = soup.find("table", id="work_outline")
        if table:
            for tr in table.find_all("tr"):
                th = tr.find("th")
                td = tr.find("td")
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
                    # 作品形式是多span带title属性
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
                    work_type = [mapping.get(span["title"].strip(), span["title"].strip()) for span in spans]

                elif key == "ファイル容量":
                    capacity_div = td.find("div", class_="main_genre")
                    raw_text = capacity_div.get_text(strip=True) if capacity_div else td.get_text(strip=True)
                    # 去掉 “総計” 等前缀
                    capacity = raw_text.replace("総計", "").strip()


        # 封面图
        cover = None
        meta_og = soup.find("meta", property="og:image")
        if meta_og and meta_og.has_attr("content"):
            cover = meta_og["content"]

        # 记录新标签映射
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
            "容量": capacity if "capacity" in locals() else None,
        }

    def batch_get_brand_extra_info_from_dlsite(self, brand_page_urls):
        print(f"⏳ [Dlsite] 批量获取品牌额外信息，数量: {len(brand_page_urls)}")

        driver = self.driver or create_silent_uc_driver()
        wait = WebDriverWait(driver, 2)

        results = {}

        try:
            for url in brand_page_urls:
                try:
                    driver.get(url)
                    link_cien_present = False
                    try:
                        link_cien_present = wait.until(
                            lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.link_cien")) > 0
                        )
                    except:
                        pass

                    if not link_cien_present:
                        print(f"⚠️ [Dlsite] 未找到 link_cien 区块（跳过）: {url}")
                        results[url] = {"官网": None, "图标": None}
                        continue

                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    link_block = soup.select_one("div.link_cien")
                    cien_link = link_block.select_one("a[href]")
                    icon_img = link_block.select_one("img[src]")

                    official_url = cien_link["href"].strip() if cien_link else None
                    icon_url = icon_img["src"].strip() if icon_img else None

                    results[url] = {"官网": official_url, "图标": icon_url}
                    print(f"✅ [Dlsite] 获取成功: 官网={official_url}, 图标={icon_url}")
                except Exception as e:
                    print(f"❌ [Dlsite] 抓取失败 {url}: {e}")
                    results[url] = {"官网": None, "图标": None}
        finally:
            if not self.external_driver and driver:
                driver.quit()
                print(f"🧹 [Dlsite] 关闭内部浏览器驱动")
        return results

    def get_brand_extra_info_from_dlsite(self, brand_page_url):
        print(f"🌐 [Dlsite] 获取品牌官网与图标: {brand_page_url}")
        if not brand_page_url:
            return {"官网": None, "图标": None}

        driver_created = False

        try:
            driver = self.driver
            if not driver:
                driver = create_silent_uc_driver()
                driver_created = True

            driver.get(brand_page_url)

            page_source = driver.page_source
            if "link_cien" not in page_source:
                print(f"⚠️ [Dlsite] 页面中未发现 link_cien")
                return {"官网": None, "图标": None}

            soup = BeautifulSoup(page_source, "html.parser")
            link_block = soup.select_one("div.link_cien")
            if not link_block:
                print(f"⚠️ [Dlsite] 无 link_cien 块")
                return {"官网": None, "图标": None}

            cien_link = link_block.select_one("a[href]")
            icon_img = link_block.select_one("img[src]")

            official_url = cien_link["href"].strip() if cien_link else None
            icon_url = icon_img["src"].strip() if icon_img else None

            print(f"✅ [Dlsite] 获取成功: 官网={official_url}, 图标={icon_url}")
            return {"官网": official_url, "图标": icon_url}

        except Exception as e:
            print(f"❌ [Dlsite] 获取品牌额外信息失败: {e}")
            return {"官网": None, "图标": None}
        finally:
            if driver_created:
                driver.quit()
                print(f"🧹 [Dlsite] 关闭内部浏览器驱动（单次）")
                driver.quit()
                print(f"🧹 [Dlsite] 关闭内部浏览器驱动（单次）")
