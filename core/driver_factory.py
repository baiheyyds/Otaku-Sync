# core/driver_factory.py
import asyncio
import threading
from typing import Dict, Optional
from concurrent.futures import Future

from selenium.webdriver.remote.webdriver import WebDriver

from utils.driver import create_driver
from utils import logger

class DriverFactory:
    """管理 Selenium WebDriver 实例的创建和销毁，并在专用线程中运行asyncio事件循环。"""

    def __init__(self):
        self._drivers: Dict[str, WebDriver] = {}
        self._creation_futures: Dict[str, Future] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._loop_started = threading.Event()

    def _run_loop(self):
        """在后台线程中运行asyncio事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_started.set() # 发出信号，表示事件循环已创建
        self._loop.run_forever()

    def start(self):
        """启动后台线程和事件循环，并等待其准备就绪。"""
        with self._lock:
            if self._thread is None:
                logger.system("正在启动驱动工厂的后台事件循环线程...")
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
                self._loop_started.wait() # 等待事件循环真正启动
                logger.system("驱动工厂后台线程已准备就绪。")

    async def create_driver_async(self, driver_key: str) -> WebDriver:
        """异步创建、缓存并返回一个 WebDriver 实例。"""
        logger.system(f"后台开始创建 {driver_key}...")
        try:
            # create_driver 是一个阻塞IO操作，应该在线程池中运行
            driver = await asyncio.to_thread(create_driver)
            self._drivers[driver_key] = driver
            logger.success(f"{driver_key} 已在后台成功创建。")
            return driver
        except Exception as e:
            logger.error(f"创建 {driver_key} 失败: {e}")
            raise

    def start_background_creation(self, driver_keys: list[str]):
        """为指定的驱动程序启动后台创建任务。"""
        self.start() # 确保后台线程已启动并准备就绪
        for key in driver_keys:
            with self._lock:
                if key not in self._creation_futures and key not in self._drivers:
                    logger.info(f"提交 {key} 的后台创建任务。")
                    # run_coroutine_threadsafe 用于从另一个线程向事件循环提交任务
                    future = asyncio.run_coroutine_threadsafe(self.create_driver_async(key), self._loop)
                    self._creation_futures[key] = future

    async def get_driver(self, driver_key: str) -> Optional[WebDriver]:
        """
        获取一个驱动实例。
        如果实例已创建，则直接返回。
        如果正在创建中，则等待创建完成。
        """
        if driver_key in self._drivers:
            return self._drivers[driver_key]

        future = self._creation_futures.get(driver_key)
        if future:
            logger.system(f"等待 {driver_key} 创建完成...")
            try:
                # 等待来自另一个线程的future完成
                driver = await asyncio.wrap_future(future)
                # 任务完成后，将其从进行中的任务列表移除
                with self._lock:
                    self._creation_futures.pop(driver_key, None)
                return driver
            except (Exception, asyncio.CancelledError) as e:
                logger.error(f"获取 {driver_key} 时发生错误: {e}")
                with self._lock:
                    self._creation_futures.pop(driver_key, None)
                return None
        
        logger.warn(f"{driver_key} 既未创建也无创建任务。可能需要先调用 start_background_creation。")
        return None

    def shutdown(self):
        """关闭所有驱动并停止后台事件循环。"""
        if not self._loop:
            return
        logger.system("正在关闭驱动工厂...")
        # 提交关闭所有驱动的任务
        if self._drivers or self._creation_futures:
            future = asyncio.run_coroutine_threadsafe(self.close_all_drivers(), self._loop)
            try:
                future.result(timeout=10) # 等待关闭完成
            except Exception as e:
                logger.error(f"关闭驱动时发生错误: {e}")

        # 停止事件循环
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        # 等待线程结束
        if self._thread:
            self._thread.join(timeout=5)
        logger.system("驱动工厂已关闭。")

    async def close_all_drivers(self):
        """关闭所有由该工厂创建的 WebDriver 实例。"""
        # 取消任何仍在进行的创建任务
        with self._lock:
            futures_to_cancel = list(self._creation_futures.values())
            for future in futures_to_cancel:
                if not future.done():
                    future.cancel()
            # 等待任务取消完成
            if futures_to_cancel:
                wrapped_futures = [asyncio.wrap_future(f) for f in futures_to_cancel]
                await asyncio.gather(*wrapped_futures, return_exceptions=True)
            self._creation_futures.clear()

        # 关闭所有已创建的驱动
        if not self._drivers:
            return

        logger.system("正在关闭所有 Selenium WebDriver 实例...")
        close_tasks = [
            asyncio.to_thread(driver.quit) for driver in self._drivers.values()
        ]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        self._drivers.clear()
        logger.system("所有 Selenium 驱动已关闭。")

# 全局唯一的 DriverFactory 实例
driver_factory = DriverFactory()
