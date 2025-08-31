# clients/fanza_client.py
import re
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from utils import logger


class FanzaClient:
    BASE_URL = "https://dlsoft.dmm.co.jp"
    SEARCH_URL = "https://dlsoft.dmm.co.jp/search/?service=pcgame&searchstr={keyword}&sort=date"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cookies = {"age_check_done": "1"}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
        }

    async def search(self, keyword: str, limit=30):
        # ... 此方法无变化 ...
        logger.info(f"[Fanza] 开始搜索: {keyword}")
        try:
            encoded_keyword = quote(keyword.encode("utf-8", errors="ignore"))
            url = self.SEARCH_URL.format(keyword=encoded_keyword)

            resp = await self.client.get(
                url, timeout=15, headers=self.headers, cookies=self.cookies
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            results = []
            result_list = soup.select_one("ul.component-legacy-productTile")
            if not result_list:
                logger.warn("[Fanza] 未找到搜索结果列表。")
                return []

            for li in result_list.find_all(
                "li", class_="component-legacy-productTile__item", limit=limit
            ):
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
                full_url = urljoin(self.BASE_URL, url_tag["href"])

                results.append(
                    {
                        "title": title,
                        "url": full_url,
                        "价格": price or "未知",
                        "类型": item_type,
                    }
                )

            initial_count = len(results)
            filtered_results = [item for item in results if "ゲーム" in item.get("类型", "")]
            exclude_keywords = ["音楽", "主題歌"]
            filtered_results = [
                item
                for item in filtered_results
                if not any(ex in item.get("title", "") for ex in exclude_keywords)
            ]
            final_count = len(filtered_results)
            logger.success(
                f"[Fanza] 找到 {initial_count} 个原始结果，筛选后剩余 {final_count} 个游戏相关结果。"
            )

            return filtered_results

        except Exception as e:
            logger.error(f"[Fanza] 搜索失败: {e}")
            return []

    async def get_game_detail(self, url: str) -> dict:
        logger.info(f"[Fanza] 正在抓取详情: {url}")
        try:
            resp = await self.client.get(
                url, timeout=15, headers=self.headers, cookies=self.cookies
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            details = {}

            # --- 提取品牌 (无变化) ---
            if top_table := soup.select_one(".contentsDetailTop__table"):
                for row in top_table.find_all("div", class_="contentsDetailTop__tableRow"):
                    key_tag = row.select_one(".contentsDetailTop__tableDataLeft p")
                    value_tag = row.select_one(".contentsDetailTop__tableDataRight")
                    if not (key_tag and value_tag):
                        continue
                    if "ブランド" in key_tag.get_text(strip=True):
                        details["品牌"] = value_tag.get_text(strip=True)

            # --- 提取详情表格信息 ---
            if bottom_table := soup.select_one(".contentsDetailBottom__table"):

                def find_row_value(header_text: str) -> Tag | None:
                    """辅助函数：通过标题找到对应的值所在的Tag"""
                    p_tag = bottom_table.find("p", string=re.compile(f"^{header_text}$"))
                    if p_tag and (parent_div := p_tag.find_parent("div")):
                        return parent_div.find_next_sibling("div")
                    return None

                # --- 提取发售日 (无变化) ---
                if value_div := find_row_value("ダウンロード版配信開始日"):
                    date_span = value_div.select_one(".item-info__release-date__content__date span")
                    date_text = (
                        date_span.get_text(strip=True)
                        if date_span
                        else value_div.get_text(strip=True)
                    )
                    if date_text:
                        details["发售日"] = date_text

                # --- 提取原画、剧本、声优 (无变化) ---
                def extract_list(value_div: Tag | None) -> list[str]:
                    if not value_div:
                        return []
                    return [a.get_text(strip=True) for a in value_div.select("li a")]

                details["原画"] = extract_list(find_row_value("原画"))
                details["剧本"] = extract_list(find_row_value("シナリオ"))
                details["声优"] = extract_list(find_row_value("声優"))

                # --- 【功能 1】智能提取游戏类别 ---
                game_types = []
                # 1.1 从 ゲームジャンル 提取
                if genre_div := find_row_value("ゲームジャンル"):
                    genre_text = genre_div.get_text(strip=True).upper()
                    if "RPG" in genre_text:
                        game_types.append("RPG")
                    if "ADV" in genre_text:
                        game_types.append("ADV")
                    if "ACT" in genre_text or "アクション" in genre_text:
                        game_types.append("ACT")
                    if "SLG" in genre_text or "シミュレーション" in genre_text:
                        game_types.append("模拟")

                # 1.2 从 ボイス 提取
                if voice_div := find_row_value("ボイス"):
                    if "あり" in voice_div.get_text(strip=True):
                        game_types.extend(["有声音", "有音乐"])

                if game_types:
                    details["作品形式"] = list(dict.fromkeys(game_types))  # 去重

                # --- 【功能 2】提取原始标签 ---
                if tags_div := find_row_value("ジャンル"):
                    # 这里只提取原始日文标签，交由TagManager处理
                    details["标签"] = [a.get_text(strip=True) for a in tags_div.select("li a")]

            # --- 提取封面、标题、价格 (无变化) ---
            if cover_img_tag := soup.select_one(".productPreview__mainImage img, #fn-main_image"):
                if cover_img_tag.has_attr("src"):
                    details["封面图链接"] = urljoin(self.BASE_URL, cover_img_tag["src"])
            if title_tag := soup.select_one("h1.productTitle__txt"):
                details["标题"] = title_tag.get_text(strip=True)
            if price_tag := soup.select_one(".priceInformation__price"):
                details["价格"] = price_tag.get_text(strip=True).replace("円", "").replace(",", "")

            return details
        except Exception as e:
            logger.error(f"[Fanza] (httpx)抓取详情失败: {e}")
            return {}
