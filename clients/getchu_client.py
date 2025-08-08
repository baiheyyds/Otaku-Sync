# clients/getchu_client.py
# GetchuClient 类用于抓取 Getchu 网站的游戏信息
import random
import re
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


class GetchuClient:
    BASE_URL = "https://www.getchu.com"
    SEARCH_URL = "https://www.getchu.com/php/nsearch.phtml"
    # AGE_CHECK_URL 不再需要，因为我们采用更直接的方式

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self._get_headers())
        # 在初始化时就完成年龄认证
        self._perform_age_check()

    def _perform_age_check(self):
        """
        修改：直接在session中手动设置年龄验证Cookie，这是最可靠的方式。
        """
        try:
            print("⏳ [Getchu] 正在手动设置年龄认证Cookie...")
            self.session.cookies.set(
                name="getchu_adalt_flag",
                value="getchu.com",
                domain=".getchu.com",  # 使用 .getchu.com 保证对所有子域名有效
            )
            print("✅ [Getchu] 'getchu_adalt_flag' Cookie已手动设置。")
        except Exception as e:
            print(f"❌ [Getchu] 手动设置Cookie失败: {e}")

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

            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()

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
                type_tag = block.select_one("span.orangeb")
                item_type = type_tag.get_text(strip=True) if type_tag else "未知"
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
                            "类型": item_type,
                        }
                    )

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
            print(f"\n🚀 [Getchu] 正在通过requests加载游戏详情页: {url}")
            # 因为cookie已经设置好，这个请求现在会直接命中详情页
            resp = self.session.get(url, timeout=15)
            resp.encoding = "euc_jp"
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # 如果成功，标题不会是'Getchu.com：R18 年齢認証'
            if "年齢認証" in soup.title.text:
                print("❌ [Getchu] 绕过年龄验证失败，页面内容不正确。")
                return {}

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
            print(f"❌ (requests)抓取失败: {e}")
            return {}
