# clients/brand_cache.py
# 该模块用于处理品牌信息的缓存
import json
import os
import shutil
from datetime import datetime

CACHE_DIR = "cache"
CACHE_FILE_NAME = "brand_extra_info_cache.json"
CACHE_FILE = os.path.join(CACHE_DIR, CACHE_FILE_NAME)


class BrandCache:
    def __init__(self, cache_file=CACHE_FILE):
        self.cache_file = cache_file
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    print(f"♻️ 已加载品牌缓存 {len(data)} 条")
                    return data
            except Exception as e:
                print(f"⚠️ 读取品牌缓存失败: {e}")
        return {}

    def save_cache(self, cache: dict):
        try:
            if not cache:
                print("⚠️ 检测到缓存数据为空，跳过保存，避免覆盖原有数据")
                return

            # 1. 备份旧缓存
            if os.path.exists(self.cache_file):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(
                    os.path.dirname(self.cache_file),
                    f"{CACHE_FILE_NAME}.bak_{timestamp}",
                )
                shutil.copy2(self.cache_file, backup_file)
                print(f"📦 已备份旧缓存为: {backup_file}")

            # 2. 写入临时文件
            tmp_file = self.cache_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            # 3. 原子替换
            os.replace(tmp_file, self.cache_file)

            print(f"💾 已保存品牌缓存 {len(cache)} 条")

            # 4. 清理旧备份
            self._cleanup_old_backups()

        except Exception as e:
            print(f"⚠️ 保存品牌缓存失败: {e}")

    def _cleanup_old_backups(self, keep_last_n=5):
        """仅保留最近 N 个备份，自动清理旧的"""
        dir_path = os.path.dirname(self.cache_file)
        prefix = f"{CACHE_FILE_NAME}.bak_"
        backup_files = sorted([f for f in os.listdir(dir_path) if f.startswith(prefix)], reverse=True)
        for old_file in backup_files[keep_last_n:]:
            try:
                os.remove(os.path.join(dir_path, old_file))
                print(f"🧹 已清理旧备份: {old_file}")
            except Exception as e:
                print(f"⚠️ 无法删除旧备份 {old_file}: {e}")
