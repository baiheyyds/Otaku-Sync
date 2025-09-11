# core/data_manager.py
import json
import os
from utils import logger

MAPPING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mapping")

class DataManager:
    def __init__(self):
        self._data = {}
        self.mapping_dir = MAPPING_DIR
        self._load_all_mappings()

    def _load_all_mappings(self):
        """加载 mapping 目录下所有的 .json 文件。"""
        if not os.path.isdir(self.mapping_dir):
            logger.error(f"映射目录不存在: {self.mapping_dir}")
            return

        for filename in os.listdir(self.mapping_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(self.mapping_dir, filename)
                # 使用文件名（不含扩展名）作为键
                key_name = os.path.splitext(filename)[0]
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # 允许空文件
                        self._data[key_name] = json.loads(content) if content else {}
                        logger.cache(f"已加载映射文件: {filename}")
                except (json.JSONDecodeError, IOError) as e:
                    logger.warn(f"加载 {filename} 失败: {e}")
                    self._data[key_name] = {}

    def get(self, key: str, default=None):
        """获取指定键的数据。"""
        return self._data.get(key, default)

    def get_all_data(self) -> dict:
        """获取所有已加载的数据。"""
        return self._data

# 创建一个全局实例，方便其他模块直接导入使用
data_manager = DataManager()
