import requests
import json
from config.config_token import BANGUMI_TOKEN

def search_bangumi(keyword):
    url = "https://api.bgm.tv/v0/search/subjects"
    headers = {
        "Authorization": f"Bearer {BANGUMI_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "BangumiTest/0.1"
    }
    payload = {
        "keyword": keyword,
        "sort": "rank",
        "filter": {
            "type": [4],
            "nsfw": True
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json()
        results = data.get("data", [])
        
        # 输出到终端
        print(f"\n✅ 关键词『{keyword}』共返回 {len(results)} 条结果：\n")
        for i, item in enumerate(results, 1):
            print(f"🔹 第 {i} 条结果：")
            print(json.dumps(item, indent=2, ensure_ascii=False))
            print("-" * 40)
        
        # 保存为 JSON 文件
        output_file = f"bangumi_search_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n📁 已保存结果到文件：{output_file}")
    else:
        print(f"❌ 请求失败，状态码: {response.status_code}")
        print("响应内容:", response.text)

if __name__ == "__main__":
    while True:
        keyword = input("请输入关键词（回车退出）：").strip()
        if not keyword:
            print("👋 退出程序。")
            break
        search_bangumi(keyword)
