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
        logger.info(f"[Fanza] 开始搜索: {keyword}")
        try:
            encoded_keyword = quote(keyword.encode("utf-8", errors="ignore"))
            url = f"/search/?service=pcgame&searchstr={encoded_keyword}&sort=date"

            resp = await self.get(url, timeout=15, cookies=self.cookies)
            if not resp:
                return []

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
                full_url = urljoin(self.base_url, url_tag["href"])

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
            # BaseClient 已经处理了请求相关的异常，这里捕获解析时的异常
            logger.error(f"[Fanza] 解析搜索结果失败: {e}")
            return []

    async def get_game_detail(self, url: str) -> dict:
        resp = await self.get(url, timeout=15, cookies=self.cookies)
        if not resp:
            return {}

        try:
            soup = BeautifulSoup(resp.text, "lxml")
            details = {}

            if top_table := soup.select_one(".contentsDetailTop__table"):
                for row in top_table.find_all("div", class_="contentsDetailTop__tableRow"):
                    key_tag = row.select_one(".contentsDetailTop__tableDataLeft p")
                    value_tag = row.select_one(".contentsDetailTop__tableDataRight")
                    if not (key_tag and value_tag):
                        continue
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
                    date_text = (
                        date_span.get_text(strip=True)
                        if date_span
                        else value_div.get_text(strip=True)
                    )
                    if date_text:
                        details["发售日"] = date_text

                def extract_list(value_div: Tag | None) -> list[str]:
                    if not value_div:
                        return []
                    return [a.get_text(strip=True) for a in value_div.select("li a")]

                # 使用循环和映射表来提取制作人员信息
                for key, value in self.STAFF_MAPPING.items():
                    # Dlsite的'イラスト'不适用于Fanza，在此跳过
                    if key == "イラスト":
                        continue
                    extracted_data = extract_list(find_row_value(key))
                    if extracted_data:
                        # 使用集合来合并，以处理'原画'和'イラスト'可能映射到同一个键的情况
                        if value in details:
                            details[value].extend(extracted_data)
                        else:
                            details[value] = extracted_data

                # 去重
                for key in details:
                    if isinstance(details[key], list):
                        details[key] = sorted(list(set(details[key])))

                game_types = []
                if genre_div := find_row_value("ゲームジャンル"):
                    genre_text = genre_div.get_text(strip=True).upper()
                    if "RPG" in genre_text: game_types.append("RPG")
                    if "ADV" in genre_text or "AVG" in genre_text: game_types.append("ADV")
                    if "ACT" in genre_text or "アクション" in genre_text: game_types.append("ACT")
                    if "SLG" in genre_text or "シミュレーション" in genre_text: game_types.append("模拟")

                if voice_div := find_row_value("ボイス"):
                    if "あり" in voice_div.get_text(strip=True):
                        game_types.extend(["有声音", "有音乐"])

                if game_types:
                    details["作品形式"] = list(dict.fromkeys(game_types))

                if tags_div := find_row_value("ジャンル"):
                    details["标签"] = [a.get_text(strip=True) for a in tags_div.select("li a")]

            if cover_img_tag := soup.select_one(".productPreview__mainImage img, #fn-main_image"):
                if cover_img_tag.has_attr("src"):
                    details["封面图链接"] = urljoin(self.base_url, cover_img_tag["src"])
            if title_tag := soup.select_one("h1.productTitle__txt"):
                details["标题"] = title_tag.get_text(strip=True)
            if price_tag := soup.select_one(".priceInformation__price"):
                details["价格"] = price_tag.get_text(strip=True).replace("円", "").replace(",", "")

            return details
        except Exception as e:
            logger.error(f"[Fanza] 解析详情页失败: {e}")
            return {}
