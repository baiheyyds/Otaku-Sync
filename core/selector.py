# core/selector.py
from utils import logger


async def select_game(dlsite_client, fanza_client, main_keyword: str, original_keyword: str):
    # 优先 DLsite 搜索
    results = await dlsite_client.search(original_keyword)
    if results:
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
                if 0 <= (selected_idx := int(choice or 0)) < len(results):
                    return results[selected_idx], "dlsite"
                else:
                    logger.error("序号超出范围，请重试。")
                    return None, None
            except (ValueError, IndexError):
                logger.error("无效输入，请输入数字、'f'或'c'。")
                return None, None
    else:
        logger.info("DLsite 未找到，尝试 Fanza 搜索...")

    # Fanza 搜索逻辑
    results = await fanza_client.search(original_keyword)
    if results:
        print("\n🔍 Fanza 找到以下结果:")
        # --- 核心修复：使用与 DLsite 相同的丰富格式 ---
        for idx, item in enumerate(results):
            price_text = item.get("价格") or item.get("price", "未知")
            price_display = f"{price_text}円" if price_text.isdigit() else price_text
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price_display} | 🏷️ {work_type}")
        # --- 修复结束 ---

        prompt = "请输入序号选择（默认0），或输入'c'取消本次操作："
        try:
            choice = input(prompt).strip().lower()
            if choice == "c":
                return None, "cancel"
            if 0 <= (selected_idx := int(choice or 0)) < len(results):
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
