# clients/brand_cache.py
# 该模块用于处理品牌信息的缓存
import json
import os
import shutil
from datetime import datetime
import hashlib

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
                    self.last_cache_hash = self._hash_content(data)
                    print(f"♻️ 已加载品牌缓存 {len(data)} 条")
                    return data
            except Exception as e:
                print(f"⚠️ 读取品牌缓存失败: {e}")
        self.last_cache_hash = None
        return {}

    def save_cache(self, cache: dict):
        try:
            if not cache:
                print("⚠️ 检测到缓存数据为空，跳过保存，避免覆盖原有数据")
                return

            new_hash = self._hash_content(cache)
            if new_hash == getattr(self, "last_cache_hash", None):
                print("ℹ️ 缓存内容无变化，跳过保存")
                return

            # 1. 备份旧缓存（每天最多一个）
            if os.path.exists(self.cache_file):
                date_str = datetime.now().strftime("%Y%m%d")
                backup_file = os.path.join(
                    os.path.dirname(self.cache_file),
                    f"{CACHE_FILE_NAME}.bak_{date_str}",
                )
                if not os.path.exists(backup_file):
                    shutil.copy2(self.cache_file, backup_file)
                    print(f"📦 已备份旧缓存为: {backup_file}")
                else:
                    print(f"📦 今日备份已存在，跳过重复备份")

            # 2. 写入临时文件
            tmp_file = self.cache_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

            # 3. 原子替换
            os.replace(tmp_file, self.cache_file)

            # 4. 保存当前 hash，避免重复保存
            self.last_cache_hash = new_hash

            print(f"💾 已保存品牌缓存 {len(cache)} 条")

            # 5. 清理旧备份（仅保留最近5天）
            self._cleanup_old_backups()

        except Exception as e:
            print(f"⚠️ 保存品牌缓存失败: {e}")

    def _cleanup_old_backups(self, keep_last_n=5):
        """仅保留最近 N 天的备份，按日期排序清理"""
        dir_path = os.path.dirname(self.cache_file)
        prefix = f"{CACHE_FILE_NAME}.bak_"
        backup_files = [f for f in os.listdir(dir_path) if f.startswith(prefix)]

        # 提取日期并排序
        dated_backups = []
        for fname in backup_files:
            try:
                date_str = fname.replace(prefix, "")
                date_obj = datetime.strptime(date_str, "%Y%m%d")
                dated_backups.append((date_obj, fname))
            except ValueError:
                continue

        # 按日期降序保留最新 N 个
        dated_backups.sort(reverse=True)
        for _, old_file in dated_backups[keep_last_n:]:
            try:
                os.remove(os.path.join(dir_path, old_file))
                print(f"🧹 已清理旧备份: {old_file}")
            except Exception as e:
                print(f"⚠️ 无法删除旧备份 {old_file}: {e}")

    def _hash_content(self, data: dict) -> str:
        """对字典内容进行哈希，以判断是否有变化"""
        try:
            serialized = json.dumps(data, sort_keys=True)
            return hashlib.md5(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return ""
