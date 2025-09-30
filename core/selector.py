# core/selector.py
import unicodedata
import re
from rapidfuzz import fuzz
from utils import logger

# 定义一个较高的相似度阈值，确保自动选择的准确性
SIMILARITY_THRESHOLD = 90  # Using rapidfuzz's scale of 0-100


def _normalize_for_selection(text: str) -> str:
    """
    A gentler normalization for selection purposes.
    - Converts to NFKC for character consistency.
    - Converts to lowercase.
    - Collapses whitespace and handles spaces around hyphens correctly.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    # Collapse whitespace and remove spaces around hyphens for consistency
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s*-\s*', '-', text)
    return text


async def search_all_sites(
    dlsite_client, fanza_client, keyword: str, site: str = "all"
) -> tuple[list, str]:
    """
    Non-interactively search DLSite and/or Fanza.
    """
    if site == "dlsite" or site == "all":
        logger.info(f"正在以 '{keyword}' 为关键词在 DLsite 上搜索...")
        results = await dlsite_client.search(keyword)
        if results:
            logger.success(f"在 DLsite 上找到 {len(results)} 个结果。")
            return results, "dlsite"
        if site == "dlsite":
            logger.error("DLsite 未找到结果。")
            return [], None

    if site == "fanza" or site == "all":
        logger.info(f"正在以 '{keyword}' 为关键词在 Fanza 上搜索...")
        results = await fanza_client.search(keyword)
        if results:
            logger.success(f"在 Fanza 上找到 {len(results)} 个结果。")
            return results, "fanza"
        if site == "fanza":
            logger.error("Fanza 未找到结果。")
            return [], None

    logger.error("所有平台均未找到结果。")
    return [], None


def _find_best_match(keyword: str, results: list) -> tuple[float, dict | None]:
    """
    Finds the best match for a keyword in a list of results using a robust scoring mechanism.
    Returns a tuple (best_score, best_item).
    """
    if not results:
        return 0, None

    norm_keyword = _normalize_for_selection(keyword)
    if not norm_keyword:
        return 0, None

    candidates = []
    for item in results:
        title = item.get("title", "")
        norm_title = _normalize_for_selection(title)
        if not norm_title:
            continue

        # Use a weighted score of different fuzzy matching methods
        # fuzz.ratio is good for overall similarity
        # fuzz.partial_ratio is good for finding substrings
        # fuzz.token_sort_ratio is good for when words are reordered
        
        r_ratio = fuzz.ratio(norm_keyword, norm_title)
        pr_ratio = fuzz.partial_ratio(norm_keyword, norm_title)
        
        # Give a strong weight to partial ratio if it indicates a substring relationship,
        # but don't let it completely dominate.
        # If one string is fully contained in the other, partial_ratio will be 100.
        if pr_ratio == 100:
            # This is a very strong signal (e.g., finding "Game" in "Game Deluxe Edition")
            # We use a high weight for the normal ratio to ensure the rest of the string also matches well.
            score = r_ratio * 0.8 + pr_ratio * 0.2
        else:
            score = r_ratio

        candidates.append((score, item))

    if not candidates:
        return 0, None

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    best_score, best_item = candidates[0]
    return best_score, best_item


async def select_game(
    dlsite_client,
    fanza_client,
    main_keyword: str,
    original_keyword: str,
    manual_mode: bool = False,
):
    """
    Searches and selects a game, with an improved auto-selection logic.
    """
    # First, try DLsite
    results = await dlsite_client.search(original_keyword)

    if results:
        if not manual_mode:
            best_score, best_match = _find_best_match(original_keyword, results)
            # Note: best_score is now 0-100
            if best_score >= SIMILARITY_THRESHOLD:
                logger.success(
                    f"[Selector] 自动选择最匹配项 (相似度: {best_score:.2f}) (来源: DLsite)"
                )
                print(f"   -> 🎮 {best_match['title']}")
                return best_match, "dlsite"

        # Manual selection fallback
        print("\n🔍 DLsite 找到以下结果:")
        for idx, item in enumerate(results):
            price_text = item.get("价格") or item.get("price", "未知")
            price_display = f"{price_text}円" if price_text.isdigit() else price_text
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price_display} | 🏷️ {work_type}")

        prompt = "请输入序号选择（默认0），输入'f'换用Fanza搜索，或输入'c'取消本次操作："
        choice = input(prompt).strip().lower()

        if choice == 'f':
            logger.info("切换到 Fanza 搜索...")
        elif choice == 'c':
            return None, "cancel"
        else:
            try:
                selected_idx = int(choice or 0)
                if 0 <= selected_idx < len(results):
                    return results[selected_idx], "dlsite"
            except (ValueError, IndexError):
                logger.error("无效输入，操作已取消。")
                return None, None
    else:
        logger.info("DLsite 未找到，尝试 Fanza 搜索...")

    # Fanza search logic
    results = await fanza_client.search(original_keyword)
    if results:
        if not manual_mode:
            best_score, best_match = _find_best_match(original_keyword, results)
            if best_score >= SIMILARITY_THRESHOLD:
                logger.success(
                    f"[Selector] 自动选择最匹配项 (相似度: {best_score:.2f}) (来源: Fanza)"
                )
                print(f"   -> 🎮 {best_match['title']}")
                return best_match, "fanza"

        # Manual selection fallback
        print("\n🔍 Fanza 找到以下结果:")
        for idx, item in enumerate(results):
            price_text = item.get("价格") or item.get("price", "未知")
            price_display = f"{price_text}円" if price_text.isdigit() else price_text
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price_display} | 🏷️ {work_type}")

        prompt = "请输入序号选择（默认0），或输入'c'取消本次操作："
        try:
            choice = input(prompt).strip().lower()
            if choice == 'c':
                return None, "cancel"
            selected_idx = int(choice or 0)
            if 0 <= selected_idx < len(results):
                return results[selected_idx], "fanza"
        except (ValueError, IndexError):
            logger.error("无效输入，操作已取消。")
            return None, None

    logger.error("所有平台均未找到结果。")
    return None, None
