# clients/brand_cache.py
# 该模块用于处理品牌信息的缓存
import hashlib
import json
import os
import shutil
import threading
from datetime import datetime

from utils import logger

CACHE_DIR = "cache"
# 将缓存文件命名得更具体，以反映其新结构和用途
CACHE_FILE_NAME = "brand_status_cache.json"
CACHE_FILE = os.path.join(CACHE_DIR, CACHE_FILE_NAME)


class BrandCache:
    def __init__(self, cache_file=CACHE_FILE):
        self.cache_file = cache_file
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        self.last_cache_hash = None
        self.cache = {}
        self.lock = threading.Lock()

    def load_cache(self):
        with self.lock:
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # 简单的数据验证，确保是期望的格式
                        if isinstance(data, dict):
                            self.cache = data
                            self.last_cache_hash = self._hash_content(self.cache)
                            logger.cache(f"已加载品牌状态缓存 {len(self.cache)} 条")
                        else:
                            logger.warn("品牌缓存文件格式不正确，将创建新缓存。")
                            self.cache = {}
                except Exception as e:
                    logger.warn(f"读取品牌状态缓存失败: {e}")
                    self.cache = {}
            return self.cache

    def save_cache(self, silent: bool = False):
        with self.lock:
            try:
                if not self.cache:
                    if not silent:
                        logger.info("检测到品牌状态缓存为空，跳过保存。")
                    return

                new_hash = self._hash_content(self.cache)
                if new_hash == self.last_cache_hash:
                    return  # 内容未变，无需保存

                # 备份旧缓存
                if os.path.exists(self.cache_file):
                    date_str = datetime.now().strftime("%Y%m%d")
                    backup_file = os.path.join(
                        os.path.dirname(self.cache_file),
                        f"{CACHE_FILE_NAME}.bak_{date_str}",
                    )
                    if not os.path.exists(backup_file):
                        shutil.copy2(self.cache_file, backup_file)

                # 原子写入
                tmp_file = self.cache_file + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, self.cache_file)

                self.last_cache_hash = new_hash
                if not silent:
                    logger.cache(f"已保存品牌状态缓存 {len(self.cache)} 条")

            except Exception as e:
                if not silent:
                    logger.error(f"保存品牌状态缓存失败: {e}")

    def get_brand_details(self, name: str) -> dict | None:
        """从缓存中获取品牌的详细信息 (page_id, has_icon)。"""
        with self.lock:
            return self.cache.get(name)

    def add_brand(self, name: str, page_id: str, has_icon: bool):
        """向缓存中添加或更新一个品牌的状态。"""
        with self.lock:
            if not name or not page_id:
                return
            self.cache[name] = {"page_id": page_id, "has_icon": has_icon}

    def _hash_content(self, data: dict) -> str:
        """对字典内容进行哈希以检查变更。"""
        try:
            serialized = json.dumps(data, sort_keys=True)
            return hashlib.md5(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return ""
