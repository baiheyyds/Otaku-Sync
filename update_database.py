import argparse
import asyncio
import difflib
import json
import os
import re
import traceback
import unicodedata
from typing import Dict, List, Optional, Set

from clients.notion_client import NotionClient
from core.init import close_context, init_context
from utils import logger
from config.config_fields import FIELDS

PROGRESS_FILE = "link_calibrate_progress.json"


# --- 工具函数部分 (无变化) ---
def load_progress() -> Set[str]:
    if not os.path.exists(PROGRESS_FILE):
        return set()
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, IOError):
        return set()


def save_progress(processed_ids: Set[str]):
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(processed_ids), f, ensure_ascii=False, indent=2)
    except IOError:
        logger.error("无法保存链接校准进度文件。")


def normalize_for_matching(title: str) -> str:
    if not title:
        return ""
    cleaned_title = re.sub(
        r"(DL版|\[DL版\]|パッケージ版|プレミアムパッケージ|通常版|体験版|豪華版|完全版|初回限定|限定版|特装版|新装版)",
        "",
        title,
        flags=re.IGNORECASE,
    )
    normalized = unicodedata.normalize("NFKC", cleaned_title).lower().strip()
    return re.sub(r"\s+", "", normalized)


async def find_best_match(
    notion_title: str, search_results: List[dict], platform: str, threshold: float
) -> Optional[str]:
    if not search_results:
        return None
    norm_notion_title = normalize_for_matching(notion_title)
    candidates = []
    for item in search_results:
        norm_item_title = normalize_for_matching(item.get("title", ""))
        ratio = difflib.SequenceMatcher(None, norm_notion_title, norm_item_title).ratio()
        if ratio >= threshold:
            candidates.append({"title": item["title"], "url": item["url"], "ratio": ratio})
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warn(
            f"  > [{platform}] 找到多个高度相似的匹配项，为保证准确性已跳过。候选: {[c['title'] for c in candidates]}"
        )
        return None
    winner = candidates[0]
    logger.success(
        f"  > [{platform}] 自动匹配成功: '{winner['title']}' (相似度: {winner['ratio']:.2%})"
    )
    return winner["url"]


async def get_all_pages(notion_client: NotionClient, db_id: str):
    all_pages = []
    next_cursor = None
    logger.info(f"正在从 Notion 获取数据库 {db_id[-6:]} 的所有页面...")
    while True:
        payload = {"start_cursor": next_cursor} if next_cursor else {}
        resp = await notion_client._request(
            "POST", f"https://api.notion.com/v1/databases/{db_id}/query", payload
        )
        if not resp:
            break
        all_pages.extend(resp.get("results", []))
        if resp.get("has_more"):
            next_cursor = resp.get("next_cursor")
        else:
            break
    logger.success(f"成功获取 {len(all_pages)} 个页面。")
    return all_pages


# --- 工具函数结束 ---


async def process_single_page(page: dict, context: dict, args):
    """
    对单个游戏页面进行链接的全面校准、迁移和补全。
    注意：此函数不再需要 semaphore 参数。
    """
    page_id = page["id"]
    props = page.get("properties", {})

    title = context["notion"].get_page_title(page)
    if not title:
        logger.warn(f"页面 (ID: {page_id[-6:]}) 缺少标题，已跳过。")
        return None

    logger.info(f"正在校准链接: '{title}'")

    current_links = {
        "official": props.get(FIELDS["game_official_url"], {}).get("url"),
        "dlsite": props.get(FIELDS["dlsite_link"], {}).get("url"),
        "fanza": props.get(FIELDS["fanza_link"], {}).get("url"),
        "bangumi": props.get(FIELDS["bangumi_url"], {}).get("url"),
    }
    update_payload = {}
    log_messages = []

    try:
        bangumi_official_url = None
        if current_links["bangumi"]:
            if match := re.search(r"/subject/(\d+)", current_links["bangumi"]):
                subject_id = match.group(1)
                game_info = await context["bangumi"].fetch_game(subject_id)
                if bgm_url := game_info.get(FIELDS["game_official_url"]):
                    bangumi_official_url = bgm_url

        if bangumi_official_url and bangumi_official_url != current_links["official"]:
            update_payload[FIELDS["game_official_url"]] = {"url": bangumi_official_url}
            log_messages.append(f"  -> [官网] 已从 Bangumi 更新。")

        if current_links["official"] and current_links["official"] != bangumi_official_url:
            old_url = current_links["official"]
            if "dlsite.com" in old_url and not current_links["dlsite"]:
                update_payload[FIELDS["dlsite_link"]] = {"url": old_url}
                log_messages.append(f"  -> [DLsite] 已从旧官网字段迁移。")
            elif ("getchu.com" in old_url or "dmm.co.jp" in old_url) and not current_links["fanza"]:
                update_payload[FIELDS["fanza_link"]] = {"url": old_url}
                log_messages.append(f"  -> [Fanza] 已从旧官网字段迁移。")

        if not update_payload.get(FIELDS["dlsite_link"]) and not current_links["dlsite"]:
            dlsite_results = await context["dlsite"].search(title)
            if dlsite_url := await find_best_match(title, dlsite_results, "DLsite", args.threshold):
                update_payload[FIELDS["dlsite_link"]] = {"url": dlsite_url}
                log_messages.append(f"  -> [DLsite] 已通过搜索补全。")

        if not update_payload.get(FIELDS["fanza_link"]) and not current_links["fanza"]:
            fanza_results = await context["fanza"].search(title)
            if fanza_url := await find_best_match(title, fanza_results, "Fanza", args.threshold):
                update_payload[FIELDS["fanza_link"]] = {"url": fanza_url}
                log_messages.append(f"  -> [Fanza] 已通过搜索补全。")

        if update_payload:
            if args.dry_run:
                logger.info(f"[试运行] 计划为 '{title}' 执行以下操作:")
                for msg in log_messages:
                    logger.info(msg)
            else:
                await context["notion"]._request(
                    "PATCH",
                    f"https://api.notion.com/v1/pages/{page_id}",
                    {"properties": update_payload},
                )
                logger.success(f"成功为 '{title}' 校准了 {len(update_payload)} 个链接。")
                for msg in log_messages:
                    print(msg)
        else:
            logger.info(f"  > '{title}' 的链接已校准且齐全，无需操作。")

        return page_id

    except Exception:
        logger.error(f"处理 '{title}' 时发生意外错误:")
        traceback.print_exc()
        return None


async def main():
    parser = argparse.ArgumentParser(description="批量为 Notion 游戏数据库校准、迁移和补全链接。")
    parser.add_argument(
        "--dry-run", action="store_true", help="试运行模式，只显示计划的操作，不实际写入 Notion。"
    )
    parser.add_argument("--batch-size", type=int, default=50, help="每个批次处理的页面数量。")
    parser.add_argument("--resume", action="store_true", help="从上次中断的地方继续。")
    parser.add_argument(
        "--threshold", type=float, default=0.9, help="自动选择的最低相似度阈值 (0.0 to 1.0)。"
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.warn("!!! 当前处于试运行模式，不会对 Notion 进行任何写入操作 !!!")

    context = await init_context()

    processed_ids = load_progress() if args.resume else set()
    if args.resume:
        logger.system(f"已加载 {len(processed_ids)} 条处理记录，将从断点处继续。")
    else:
        logger.system("从头开始更新，旧的进度将被覆盖。")

    try:
        all_pages = await get_all_pages(context["notion"], context["notion"].game_db_id)
        pages_to_process = [p for p in all_pages if p["id"] not in processed_ids]

        if not pages_to_process:
            logger.success("所有游戏条目均已处理过，无需更新。")
            return

        logger.system(f"开始处理 {len(pages_to_process)} 个游戏条目...")

        # --- 核心修复：从并发 gather 切换到顺序 for 循环 ---
        processed_count_in_session = 0
        for i, page in enumerate(pages_to_process):
            # 打印当前进度
            logger.system(
                f"--- 正在处理第 {i+1} / {len(pages_to_process)} 个 (总进度: {len(processed_ids) + i + 1} / {len(all_pages)}) ---"
            )

            result_id = await process_single_page(page, context, args)

            if result_id:
                processed_ids.add(result_id)
                processed_count_in_session += 1

            # 每处理完一个就保存一次进度，或者每处理N个保存一次，这里选择每10个
            if (i + 1) % 10 == 0:
                save_progress(processed_ids)
                logger.info("已自动保存进度。")

        # 循环结束后再保存一次，确保最后几个也被记录
        save_progress(processed_ids)
        # --- 修复结束 ---

        logger.success(
            f"本次运行共处理了 {processed_count_in_session} 个条目。所有链接校准任务已完成！"
        )

    except Exception:
        logger.error("链接校准过程中发生严重错误:")
        traceback.print_exc()
    finally:
        logger.system("正在清理资源...")
        await close_context(context)
        logger.system("程序已安全退出。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被强制退出。")
