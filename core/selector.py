# core/selector.py
# 该模块用于选择游戏
def select_game(dlsite_client, getchu_client, main_keyword: str, original_keyword: str):
    # 优先 DLsite 搜索
    results = dlsite_client.search(original_keyword)
    if results:
        print("\n🔍 手动选择游戏:")
        for idx, item in enumerate(results):
            price = item.get("价格") or item.get("price") or "未知"
            work_type = item.get("类型") or "未知"
            print(f"[{idx}] 🎮 {item['title']} | 💴 {price} | 🏷️ {work_type}")
        choice = input("请输入序号选择（默认0），或输入 'g' 使用 Getchu 搜索：").strip().lower()
        if choice == 'g':
            # 跳到 Getchu 搜索
            print("🔁 正在使用 Getchu 搜索...")
        else:
            try:
                selected = int(choice or 0)
                return results[selected], "dlsite"
            except (ValueError, IndexError):
                print("❌ 无效选择")
                return None, None

    else:
        print("❌ DLsite 未找到，尝试 Getchu 搜索...")

    # Getchu 搜索
    results = getchu_client.search(original_keyword)
    if results:
        print("\n🔍 手动选择游戏（Getchu）:")
        print("\n🔍 手动选择游戏（Getchu）:")
        for idx, item in enumerate(results):
            print(f"[{idx}] 🎮 {item['title']} | 💴 {item.get('价格') or item.get('price', '未知')}円 | 📦 类型: {item.get('类型', '未知')}")
        try:
            selected = int(input("请输入序号选择（默认0）：") or 0)
            return results[selected], "getchu"
        except (ValueError, IndexError):
            print("❌ 无效选择")
            return None, None
    else:
        print("❌ Getchu 未找到结果")
        return None, None
