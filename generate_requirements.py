import os
import sys
import subprocess
import shutil
import datetime

def run_cmd(cmd):
    """运行命令并返回状态码"""
    print(f"▶ 执行: {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode

def backup_requirements(req_path):
    """备份已存在的 requirements.txt"""
    if os.path.exists(req_path):
        backup_name = f"{req_path}.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy(req_path, backup_name)
        print(f"🗂 已备份原 requirements.txt 到 {backup_name}")

def generate_with_pipreqs(project_path, req_path):
    """尝试用 pipreqs 生成 requirements.txt"""
    try:
        import pipreqs  # 检查 pipreqs 是否安装
    except ImportError:
        print("⚠️ 未检测到 pipreqs，正在安装...")
        run_cmd(f"{sys.executable} -m pip install pipreqs")

    print("📦 正在用 pipreqs 生成 requirements.txt（仅包含项目用到的包）...")
    # 优先尝试 python -m pipreqs
    ret = run_cmd(f"{sys.executable} -m pipreqs {project_path} --encoding=utf-8 --force")
    if ret != 0:
        print("⚠️ 检测到 pipreqs 无法用 -m 方式执行，尝试直接调用 pipreqs 命令...")
        ret = run_cmd(f"pipreqs {project_path} --encoding=utf-8 --force")
    return ret == 0

def generate_with_pip_freeze(req_path):
    """用 pip freeze 生成 requirements.txt"""
    print("📦 正在用 pip freeze 生成 requirements.txt（包含当前环境全部包）...")
    with open(req_path, "w", encoding="utf-8") as f:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=f)

if __name__ == "__main__":
    project_dir = os.path.dirname(os.path.abspath(__file__))
    req_file = os.path.join(project_dir, "requirements.txt")

    backup_requirements(req_file)

    print("请选择生成方式：")
    print("1️⃣  pipreqs（推荐，仅包含项目实际 import 的包）")
    print("2️⃣  pip freeze（包含当前环境全部包）")
    choice = input("请输入 1 或 2（直接回车=1）：").strip() or "1"

    success = False
    if choice == "1":
        success = generate_with_pipreqs(project_dir, req_file)
        if not success:
            print("⚠️ pipreqs 生成失败，自动切换到 pip freeze...")
            generate_with_pip_freeze(req_file)
    elif choice == "2":
        generate_with_pip_freeze(req_file)
    else:
        print("❌ 无效选择，已退出。")

    if os.path.exists(req_file):
        print(f"✅ requirements.txt 已生成：{req_file}")
    else:
        print("❌ 生成失败，没有找到 requirements.txt")
