# core/selector.py
# 该模块用于选择游戏
def select_game(dlsite_client, getchu_client, main_keyword: str, original_keyword: str):
    # 优先 DLsite 搜索
    results = dlsite_client.search(original_keyword)
    if results:
        print("\n🔍 DLsite 找到以下结果:")
        for idx, item in enumerate(results):
            price = item.get("价格") or item.get("price") or "未知"
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price} | 🏷️ {work_type}")

        # 修改提示，增加取消选项 'c'
        prompt = "请输入序号选择（默认0），输入 'g' 换用Getchu搜索，或输入 'c' 取消本次操作："
        choice = input(prompt).strip().lower()

        if choice == "g":
            # 跳到 Getchu 搜索
            print("🔁 正在使用 Getchu 搜索...")
        elif choice == 'c':
            return None, "cancel"  # 返回特殊状态表示取消
        else:
            try:
                selected_idx = int(choice or 0)
                if 0 <= selected_idx < len(results):
                    return results[selected_idx], "dlsite"
                else:
                    print("❌ 序号超出范围，请重试。")
                    return None, None
            except (ValueError, IndexError):
                print("❌ 无效输入，请输入数字、'g'或'c'。")
                return None, None

    else:
        print("❌ DLsite 未找到，尝试 Getchu 搜索...")

    # Getchu 搜索
    results = getchu_client.search(original_keyword)
    if results:
        print("\n🔍 手动选择游戏（Getchu）:")
        for idx, item in enumerate(results):
            print(
                f"[{idx}] 🎮 {item['title']} | 💴 {item.get('价格') or item.get('price', '未知')}円 | 📦 类型: {item.get('类型', '未知')}"
            )
        
        # 修改提示，增加取消选项 'c'
        prompt = "请输入序号选择（默认0），或输入 'c' 取消本次操作："
        try:
            choice = input(prompt).strip().lower()
            if choice == 'c':
                return None, "cancel" # 返回特殊状态表示取消

            selected_idx = int(choice or 0)
            if 0 <= selected_idx < len(results):
                return results[selected_idx], "getchu"
            else:
                print("❌ 序号超出范围，请重试。")
                return None, None
        except (ValueError, IndexError):
            print("❌ 无效输入，请输入数字或'c'。")
            return None, None
    else:
        print("❌ Getchu 未找到结果")
        return None, None