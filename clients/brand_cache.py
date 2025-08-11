# clients/brand_cache.py
# 该模块用于处理品牌信息的缓存
import hashlib
import json
import os
import shutil
from datetime import datetime

from utils import logger

CACHE_DIR = "cache"
CACHE_FILE_NAME = "brand_extra_info_cache.json"
CACHE_FILE = os.path.join(CACHE_DIR, CACHE_FILE_NAME)


class BrandCache:
    def __init__(self, cache_file=CACHE_FILE):
        self.cache_file = cache_file
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        self.last_cache_hash = None

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_cache_hash = self._hash_content(data)
                    logger.cache(f"已加载品牌缓存 {len(data)} 条")
                    return data
            except Exception as e:
                logger.warn(f"读取品牌缓存失败: {e}")
        return {}

    def save_cache(self, cache: dict):
        try:
            if not cache:
                logger.info("检测到缓存数据为空，跳过保存，避免覆盖原有数据")
                return

            new_hash = self._hash_content(cache)
            if new_hash == self.last_cache_hash:
                return

            # 1. Backup old cache
            if os.path.exists(self.cache_file):
                date_str = datetime.now().strftime("%Y%m%d")
                backup_file = os.path.join(
                    os.path.dirname(self.cache_file), f"{CACHE_FILE_NAME}.bak_{date_str}"
                )
                if not os.path.exists(backup_file):
                    shutil.copy2(self.cache_file, backup_file)
                    logger.cache(f"已备份旧缓存为: {os.path.basename(backup_file)}")

            # 2. Atomic write
            tmp_file = self.cache_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.cache_file)

            self.last_cache_hash = new_hash
            logger.cache(f"已保存品牌缓存 {len(cache)} 条")

            # 3. Cleanup old backups
            self._cleanup_old_backups()

        except Exception as e:
            logger.error(f"保存品牌缓存失败: {e}")

    def _cleanup_old_backups(self, keep_last_n=5):
        """Keeps the last N daily backups."""
        dir_path = os.path.dirname(self.cache_file)
        prefix = f"{CACHE_FILE_NAME}.bak_"
        backup_files = [f for f in os.listdir(dir_path) if f.startswith(prefix)]

        dated_backups = []
        for fname in backup_files:
            try:
                date_obj = datetime.strptime(fname.replace(prefix, ""), "%Y%m%d")
                dated_backups.append((date_obj, fname))
            except ValueError:
                continue

        dated_backups.sort(reverse=True)
        for _, old_file in dated_backups[keep_last_n:]:
            try:
                os.remove(os.path.join(dir_path, old_file))
                logger.system(f"已清理旧备份: {old_file}")
            except Exception as e:
                logger.warn(f"无法删除旧备份 {old_file}: {e}")

    def _hash_content(self, data: dict) -> str:
        """Hashes dictionary content to check for changes."""
        try:
            serialized = json.dumps(data, sort_keys=True)
            return hashlib.md5(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return ""
