# core/selector.py
import difflib
from utils import logger
from utils.similarity_check import normalize

# 定义一个较高的相似度阈值，确保自动选择的准确性
# 只有当匹配度 >= 90% 时，才会自动选择
SIMILARITY_THRESHOLD = 0.9


def _find_best_match(keyword: str, results: list) -> tuple[float, dict | None]:
    """
    在结果列表中找到与关键词最匹配的项。
    返回一个元组 (最高相似度分数, 最佳匹配项)。
    """
    if not results:
        return 0, None

    norm_keyword = normalize(keyword)
    if not norm_keyword:
        return 0, None

    candidates = []
    for item in results:
        title = item.get("title", "")
        norm_title = normalize(title)
        if not norm_title:
            continue

        ratio = difflib.SequenceMatcher(None, norm_keyword, norm_title).ratio()

        # 如果是子字符串关系，这是一个非常强的匹配信号，可以给予额外加成
        if norm_keyword in norm_title or norm_title in norm_keyword:
            ratio = max(ratio, 0.95)

        candidates.append((ratio, item))

    if not candidates:
        return 0, None

    # 按相似度降序排序
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]  # 返回 (best_score, best_item)


async def select_game(
    dlsite_client,
    fanza_client,
    main_keyword: str,
    original_keyword: str,
    manual_mode: bool = False,
):
    """
    搜索并选择游戏。
    如果找到一个高度匹配的结果且不处于手动模式，则自动选择。
    否则，显示列表供用户手动选择。
    """
    # 优先 DLsite 搜索
    results = await dlsite_client.search(original_keyword)

    if results:
        # --- 智能选择逻辑 ---
        if not manual_mode:
            best_score, best_match = _find_best_match(original_keyword, results)
            if best_score >= SIMILARITY_THRESHOLD:
                logger.success(
                    f"[Selector] 自动选择最匹配项 (相似度: {best_score:.2f}) (来源: DLsite)"
                )
                print(f"   -> 🎮 {best_match['title']}")
                return best_match, "dlsite"
        # --- 自动选择逻辑结束，以下为手动选择流程 ---

        print("\n🔍 DLsite 找到以下结果:")
        for idx, item in enumerate(results):
            price_text = item.get("价格") or item.get("price", "未知")
            price_display = f"{price_text}円" if price_text.isdigit() else price_text
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price_display} | 🏷️ {work_type}")

        prompt = "请输入序号选择（默认0），输入'f'换用Fanza搜索，或输入'c'取消本次操作："
        choice = input(prompt).strip().lower()

        if choice == "f":
            logger.info("切换到 Fanza 搜索...")
        elif choice == "c":
            return None, "cancel"
        else:
            try:
                selected_idx = int(choice or 0)
                if 0 <= selected_idx < len(results):
                    return results[selected_idx], "dlsite"
                else:
                    logger.error("序号超出范围，请重试。")
                    return None, None
            except (ValueError, IndexError):
                logger.error("无效输入，请输入数字、'f'或'c'。")
                return None, None
    else:
        logger.info("DLsite 未找到，尝试 Fanza 搜索...")

    # Fanza 搜索逻辑 (同样加入智能选择)
    results = await fanza_client.search(original_keyword)
    if results:
        # --- 智能选择逻辑 ---
        if not manual_mode:
            best_score, best_match = _find_best_match(original_keyword, results)
            if best_score >= SIMILARITY_THRESHOLD:
                logger.success(
                    f"[Selector] 自动选择最匹配项 (相似度: {best_score:.2f}) (来源: Fanza)"
                )
                print(f"   -> 🎮 {best_match['title']}")
                return best_match, "fanza"
        # --- 自动选择逻辑结束 ---

        print("\n🔍 Fanza 找到以下结果:")
        for idx, item in enumerate(results):
            price_text = item.get("价格") or item.get("price", "未知")
            price_display = f"{price_text}円" if price_text.isdigit() else price_text
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price_display} | 🏷️ {work_type}")

        prompt = "请输入序号选择（默认0），或输入'c'取消本次操作："
        try:
            choice = input(prompt).strip().lower()
            if choice == "c":
                return None, "cancel"
            selected_idx = int(choice or 0)
            if 0 <= selected_idx < len(results):
                return results[selected_idx], "fanza"
            else:
                logger.error("序号超出范围，请重试。")
                return None, None
        except (ValueError, IndexError):
            logger.error("无效输入，请输入数字或'c'。")
            return None, None
    else:
        logger.error("Fanza 未找到结果")
        return None, None
