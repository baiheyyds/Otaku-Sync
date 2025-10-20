# config/config_token.py
# 该模块现在负责从环境变量中安全地加载配置信息

import os
import sys

from dotenv import load_dotenv

# 从项目根目录的 .env 文件中加载环境变量
# 这使得脚本无论从哪里运行都能找到 .env 文件
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(project_root, ".env")

if not os.path.exists(dotenv_path):
    print("❌ [配置错误] 未找到 .env 文件！")
    print("   请将项目根目录下的 .env.example 文件复制为 .env，并填入你的配置信息。")
    sys.exit(1)  # 直接退出

load_dotenv(dotenv_path=dotenv_path)

# --- 从环境变量中读取配置 ---
# os.getenv("KEY") 会读取名为 "KEY" 的环境变量，如果不存在则返回 None
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
GAME_DB_ID = os.getenv("GAME_DB_ID")
BRAND_DB_ID = os.getenv("BRAND_DB_ID")
STATS_DB_ID = os.getenv("STATS_DB_ID")
BANGUMI_TOKEN = os.getenv("BANGUMI_TOKEN")
CHARACTER_DB_ID = os.getenv("CHARACTER_DB_ID")

# --- 启动时检查，确保关键配置已成功加载 ---
# 这是严谨性检查，可以防止因 .env 文件缺失或拼写错误导致的后续问题
# 程序会立即失败并给出清晰的错误提示，而不是在运行时随机出错
CRITICAL_VARS = {
    "NOTION_TOKEN": NOTION_TOKEN,
    "GAME_DB_ID": GAME_DB_ID,
    "BRAND_DB_ID": BRAND_DB_ID,
    "BANGUMI_TOKEN": BANGUMI_TOKEN,
    "CHARACTER_DB_ID": CHARACTER_DB_ID,
}

missing_vars = [name for name, value in CRITICAL_VARS.items() if not value]

if missing_vars:
    # 使用 logger 可能会导致循环导入，此处用 print 更安全
    print(f"❌ [配置错误] 关键配置信息缺失: {', '.join(missing_vars)}")
    print("   请检查你的 .env 文件，确保所有必要的 TOKEN 和 DB_ID 都已正确填写。")
    # 抛出 ValueError 会直接中断程序启动，防止带着错误的配置运行
    raise ValueError("Environment configuration error.")
