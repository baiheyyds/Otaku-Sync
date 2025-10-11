# clients/fanza_client.py
import re
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Tag

from utils import logger
from .base_client import BaseClient


class FanzaClient(BaseClient):
    def __init__(self, client):
        super().__init__(client, base_url="https://dlsoft.dmm.co.jp")
        self.cookies = {"age_check_done": "1"}

    async def search(self, keyword: str, limit=30):
        logger.info(f"[Fanza] 开始主搜索 (dlsoft): {keyword}")
        try:
            # --- 主搜索逻辑 (使用 dlsoft) ---
            encoded_keyword = quote(keyword.encode("utf-8", errors="ignore"))
            url = f"/search/?service=pcgame&searchstr={encoded_keyword}&sort=date"
            resp = await self.get(url, timeout=15, cookies=self.cookies)
            
            results = []
            if resp:
                soup = BeautifulSoup(resp.text, "lxml")
                result_list = soup.select_one("ul.component-legacy-productTile")
                if result_list:
                    for li in result_list.find_all("li", class_="component-legacy-productTile__item", limit=limit):
                        title_tag = li.select_one(".component-legacy-productTile__title")
                        price_tag = li.select_one(".component-legacy-productTile__price")
                        url_tag = li.select_one("a.component-legacy-productTile__detailLink")
                        type_tag = li.select_one(".component-legacy-productTile__relatedInfo")
                        item_type = type_tag.get_text(strip=True) if type_tag else "未知"

                        if not (title_tag and url_tag and url_tag.has_attr("href")):
                            continue

                        title = title_tag.get_text(strip=True)
                        price_text = price_tag.get_text(strip=True) if price_tag else "未知"
                        price = price_text.split("円")[0].replace(",", "").strip()
                        full_url = urljoin(self.base_url, url_tag["href"])

                        results.append({
                            "title": title, "url": full_url,
                            "价格": price or "未知", "类型": item_type,
                        })

            # --- 筛选主搜索结果 ---
            initial_count = len(results)
            filtered_results = [item for item in results if "ゲーム" in item.get("类型", "")]
            exclude_keywords = ["音楽", "主題歌"]
            filtered_results = [
                item for item in filtered_results
                if not any(ex in item.get("title", "") for ex in exclude_keywords)
            ]
            final_count = len(filtered_results)

            if final_count > 0:
                logger.success(f"[Fanza] 主搜索成功，找到 {initial_count} 个原始结果，筛选后剩余 {final_count} 个游戏。")
                return filtered_results
            
            # --- 后备搜索逻辑 (如果主搜索无结果) ---
            logger.warn("[Fanza] 主搜索 (dlsoft) 未找到结果，尝试后备搜索 (mono)...")
            
            fallback_base_url = "https://www.dmm.co.jp"
            url_fallback = f"{fallback_base_url}/mono/-/search/=/searchstr={encoded_keyword}/sort=date/"
            
            resp_fallback = await self.get(url_fallback, timeout=15, cookies=self.cookies)
            if not resp_fallback:
                logger.error("[Fanza] 后备搜索请求失败。")
                return []

            soup_fallback = BeautifulSoup(resp_fallback.text, "lxml")
            results_fallback = []
            result_list_fallback = soup_fallback.select_one("#list")
            if not result_list_fallback:
                logger.warn("[Fanza] 后备搜索未找到结果列表 (#list)。")
                return []

            for li in result_list_fallback.find_all("li", limit=limit):
                url_tag = li.select_one(".tmb a")
                if not url_tag: continue
                
                title_tag = url_tag.select_one(".txt")
                price_tag = li.select_one(".price")

                if not (title_tag and url_tag.has_attr("href")): continue

                title = title_tag.get_text(strip=True)
                price_text = price_tag.get_text(strip=True) if price_tag else "未知"
                price = price_text.split("円")[0].replace(",", "").strip()
                full_url = urljoin(fallback_base_url, url_tag["href"])

                results_fallback.append({
                    "title": title, "url": full_url,
                    "价格": price or "未知", "类型": "未知(后备)",
                })
            
            initial_count_fallback = len(results_fallback)
            filtered_results_fallback = [
                item for item in results_fallback
                if not any(ex in item.get("title", "") for ex in exclude_keywords)
            ]
            final_count_fallback = len(filtered_results_fallback)
            logger.success(f"[Fanza] 后备搜索成功，找到 {initial_count_fallback} 个原始结果，筛选后剩余 {final_count_fallback} 个。")
            return filtered_results_fallback

        except Exception as e:
            logger.error(f"[Fanza] 搜索过程中出现意外错误: {e}")
            return []

    async def get_game_detail(self, url: str) -> dict:
        resp = await self.get(url, timeout=15, cookies=self.cookies)
        if not resp:
            return {}

        try:
            soup = BeautifulSoup(resp.text, "lxml")
            details = {}

            # ==================================================================
            # 智能解析：根据URL判断使用哪套解析逻辑
            # ==================================================================
            if "/mono/" in url:
                # --- 旧版/后备接口 (`/mono/`) 的解析逻辑 ---
                logger.info("[Fanza] 检测到 /mono/ 链接，使用旧版表格解析器。")
                
                if title_tag := soup.select_one("h1#title"):
                    details["标题"] = title_tag.get_text(strip=True)
                
                if cover_tag := soup.select_one("#sample-video img, .area-img img"):
                     if src := cover_tag.get("src"):
                        details["封面图链接"] = urljoin(self.base_url, src)

                if main_table := soup.select_one("table.mg-b20"):
                    rows = main_table.find_all("tr")
                    for row in rows:
                        cells = row.find_all("td")
                        if len(cells) < 2: continue
                        
                        key = cells[0].get_text(strip=True)
                        value_cell = cells[1]

                        if "発売日" in key:
                            details["发售日"] = value_cell.get_text(strip=True)
                        elif "ブランド" in key:
                            details["品牌"] = value_cell.get_text(strip=True)
                        elif "原画" in key:
                            details["原画"] = [a.get_text(strip=True) for a in value_cell.find_all("a")]
                        elif "シナリオ" in key:
                            details["剧本"] = [a.get_text(strip=True) for a in value_cell.find_all("a")]
                        elif key.startswith("ジャンル"):
                            details["标签"] = [a.get_text(strip=True) for a in value_cell.find_all("a")]
                        elif "ゲームジャンル" in key:
                            game_types = details.get("作品形式", [])
                            genre_text = value_cell.get_text(strip=True).upper()
                            for genre_key, genre_value in self._genre_reverse_mapping.items():
                                if genre_key in genre_text: game_types.append(genre_value)
                            if game_types: details["作品形式"] = list(dict.fromkeys(game_types))
                        elif "ボイス" in key:
                            if "あり" in value_cell.get_text(strip=True):
                                game_types = details.get("作品形式", [])
                                game_types.extend(["有声音", "有音乐"])
                                details["作品形式"] = list(dict.fromkeys(game_types))
            else:
                # --- 新版/主接口 (`dlsoft`) 的解析逻辑 (现有逻辑) ---
                logger.info("[Fanza] 未检测到 /mono/ 链接，使用新版解析器。")
                if top_table := soup.select_one(".contentsDetailTop__table"):
                    for row in top_table.find_all("div", class_="contentsDetailTop__tableRow"):
                        key_tag = row.select_one(".contentsDetailTop__tableDataLeft p")
                        value_tag = row.select_one(".contentsDetailTop__tableDataRight")
                        if not (key_tag and value_tag): continue
                        if "ブランド" in key_tag.get_text(strip=True):
                            details["品牌"] = value_tag.get_text(strip=True)

                if bottom_table := soup.select_one(".contentsDetailBottom__table"):
                    def find_row_value(header_text: str) -> Tag | None:
                        p_tag = bottom_table.find("p", string=re.compile(f"^{header_text}$"))
                        if p_tag and (parent_div := p_tag.find_parent("div")):
                            return parent_div.find_next_sibling("div")
                        return None

                    if value_div := find_row_value("ダウンロード版配信開始日"):
                        date_span = value_div.select_one(".item-info__release-date__content__date span")
                        date_text = (date_span.get_text(strip=True) if date_span else value_div.get_text(strip=True))
                        if date_text: details["发售日"] = date_text

                    def extract_list(value_div: Tag | None) -> list[str]:
                        if not value_div: return []
                        return [a.get_text(strip=True) for a in value_div.select("li a")]

                    for key, value in self.STAFF_MAPPING.items():
                        if key == "イラスト": continue
                        extracted_data = extract_list(find_row_value(key))
                        if extracted_data:
                            if value in details: details[value].extend(extracted_data)
                            else: details[value] = extracted_data

                    for key in details:
                        if isinstance(details[key], list): details[key] = sorted(list(set(details[key])))

                    game_types = []
                    if genre_div := find_row_value("ゲームジャンル"):
                        genre_text = genre_div.get_text(strip=True).upper()
                        for key, value in self._genre_reverse_mapping.items():
                            if key in genre_text: game_types.append(value)

                    if voice_div := find_row_value("ボイス"):
                        if "あり" in voice_div.get_text(strip=True): game_types.extend(["有声音", "有音乐"])

                    if game_types: details["作品形式"] = list(dict.fromkeys(game_types))

                    if tags_div := find_row_value("ジャンル"):
                        details["标签"] = [a.get_text(strip=True) for a in tags_div.select("li a")]

                if cover_tag := soup.find("meta", property="og:image"):
                    details["封面图链接"] = urljoin(self.base_url, cover_tag["content"])
                else:
                    cover_selector = (".productPreview__mainImage img, #fn-main_image, .main-visual img")
                    if cover_img_tag := soup.select_one(cover_selector):
                        if src := cover_img_tag.get("src"): details["封面图链接"] = urljoin(self.base_url, src)
                
                if title_tag := soup.select_one("h1.productTitle__txt"):
                    details["标题"] = title_tag.get_text(strip=True)
                if price_tag := soup.select_one(".priceInformation__price"):
                    details["价格"] = price_tag.get_text(strip=True).replace("円", "").replace(",", "")

            return details
        except Exception as e:
            logger.error(f"[Fanza] 解析详情页失败: {e}")
            return {}
