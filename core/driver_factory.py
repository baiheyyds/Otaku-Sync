# core/driver_factory.py
import asyncio
from typing import Dict, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from utils.driver import create_driver
from utils import logger

class DriverFactory:
    """管理 Selenium WebDriver 实例的创建和销毁。"""

    def __init__(self):
        self._drivers: Dict[str, WebDriver] = {}
        self._creation_tasks: Dict[str, asyncio.Task] = {}

    async def create_driver_async(self, driver_key: str) -> WebDriver:
        """异步创建、缓存并返回一个 WebDriver 实例。"""
        logger.system(f"后台开始创建 {driver_key}...")
        try:
            driver = await asyncio.to_thread(create_driver)
            self._drivers[driver_key] = driver
            logger.success(f"{driver_key} 已在后台成功创建。")
            return driver
        except Exception as e:
            logger.error(f"创建 {driver_key} 失败: {e}")
            raise

    def start_background_creation(self, driver_keys: list[str]):
        """为指定的驱动程序启动后台创建任务。"""
        for key in driver_keys:
            if key not in self._creation_tasks:
                self._creation_tasks[key] = asyncio.create_task(self.create_driver_async(key))

    async def get_driver(self, driver_key: str) -> Optional[WebDriver]:
        """
        获取一个驱动实例。
        如果实例已创建，则直接返回。
        如果正在创建中，则等待创建完成。
        """
        if driver_key in self._drivers:
            return self._drivers[driver_key]

        if driver_key in self._creation_tasks:
            logger.system(f"等待 {driver_key} 创建完成...")
            try:
                driver = await self._creation_tasks[driver_key]
                return driver
            except (Exception, asyncio.CancelledError) as e:
                logger.error(f"获取 {driver_key} 时发生错误: {e}")
                # 任务失败或被取消后，从任务列表中移除，以便可以重试
                del self._creation_tasks[driver_key]
                return None
        
        logger.warn(f"{driver_key} 既未创建也无创建任务。")
        return None

    async def close_all_drivers(self):
        """关闭所有由该工厂创建的 WebDriver 实例。"""
        # 取消任何仍在进行的创建任务
        for task in self._creation_tasks.values():
            if not task.done():
                task.cancel()
        
        # 等待任务取消完成
        await asyncio.gather(*self._creation_tasks.values(), return_exceptions=True)

        # 关闭所有已创建的驱动
        if not self._drivers:
            return

        logger.system("正在关闭所有 Selenium WebDriver 实例...")
        close_tasks = [
            asyncio.to_thread(driver.quit) for driver in self._drivers.values()
        ]
        await asyncio.gather(*close_tasks, return_exceptions=True)
        self._drivers.clear()
        logger.system("所有 Selenium 驱动已关闭。")

# 全局唯一的 DriverFactory 实例
driver_factory = DriverFactory()
