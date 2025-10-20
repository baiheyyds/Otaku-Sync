# core/driver_factory.py
import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Dict, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from utils.driver import create_driver


class DriverFactory:
    """管理 Selenium WebDriver 实例的创建和销毁，并在专用线程中运行asyncio事件循环。"""

    def __init__(self):
        self._drivers: Dict[str, WebDriver] = {}
        self._creation_futures: Dict[str, Future] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock() # 用于保护 self._drivers 和 self._creation_futures 的线程锁
        self._loop_started = threading.Event()
        self._creation_lock: Optional[asyncio.Lock] = None # 用于序列化驱动创建的异步锁

    def _run_loop(self):
        """在后台线程中运行asyncio事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._creation_lock = asyncio.Lock() # 在事件循环内初始化异步锁
        self._loop_started.set() # 发出信号，表示事件循环已创建
        self._loop.run_forever()

    def start(self):
        """启动后台线程和事件循环，并等待其准备就绪。"""
        with self._lock:
            if self._thread is None:
                logging.info("🔧 正在启动驱动工厂的后台事件循环线程...")
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
                self._loop_started.wait() # 等待事件循环真正启动
                logging.info("🔧 驱动工厂后台线程已准备就绪。")

    async def create_driver_async(self, driver_key: str) -> WebDriver:
        """异步创建、缓存并返回一个 WebDriver 实例。使用锁来防止并发创建。"""
        # 使用 asyncio.Lock 序列化驱动创建过程，防止 webdriver-manager 的并发问题
        assert self._creation_lock is not None
        async with self._creation_lock:
            # 再次检查，以防在等待锁期间驱动已被其他协程创建
            with self._lock:
                if driver_key in self._drivers:
                    return self._drivers[driver_key]

            logging.info(f"🔧 后台开始创建 {driver_key}...")
            try:
                # create_driver 是一个阻塞IO操作，应该在线程池中运行
                driver = await asyncio.to_thread(create_driver)
                with self._lock:
                    self._drivers[driver_key] = driver
                logging.info(f"✅ {driver_key} 已在后台成功创建。")
                return driver
            except Exception as e:
                logging.error(f"❌ 创建 {driver_key} 失败: {e}")
                raise

    def start_background_creation(self, driver_keys: list[str]):
        """为指定的驱动程序启动后台创建任务。"""
        self.start() # 确保后台线程已启动并准备就绪
        for key in driver_keys:
            with self._lock:
                if key not in self._creation_futures and key not in self._drivers:
                    logging.info(f"🔧 提交 {key} 的后台创建任务。")
                    # run_coroutine_threadsafe 用于从另一个线程向事件循环提交任务
                    assert self._loop is not None
                    future = asyncio.run_coroutine_threadsafe(self.create_driver_async(key), self._loop)
                    self._creation_futures[key] = future

    async def get_driver(self, driver_key: str) -> Optional[WebDriver]:
        """
        获取一个驱动实例。
        如果实例已创建，则直接返回。
        如果正在创建中，则等待创建完成。
        """
        with self._lock:
            if driver_key in self._drivers:
                return self._drivers[driver_key]

            future = self._creation_futures.get(driver_key)

        if future:
            logging.info(f"🔧 等待 {driver_key} 创建完成...")
            try:
                # 等待来自另一个线程的future完成
                driver = await asyncio.wrap_future(future)
                # 任务完成后，将其从进行中的任务列表移除
                with self._lock:
                    self._creation_futures.pop(driver_key, None)
                return driver
            except (Exception, asyncio.CancelledError) as e:
                logging.error(f"❌ 获取 {driver_key} 时发生错误: {e}")
                with self._lock:
                    self._creation_futures.pop(driver_key, None)
                return None

        logging.warning(f"⚠️ {driver_key} 既未创建也无创建任务。可能需要先调用 start_background_creation。")
        return None

    def shutdown_sync(self):
        """同步关闭所有驱动并停止后台事件循环。会阻塞调用线程。"""
        if not self._loop:
            return
        logging.info("🔧 正在关闭驱动工厂...")

        has_work = False
        with self._lock:
            if self._drivers or self._creation_futures:
                has_work = True

        if has_work:
            future = asyncio.run_coroutine_threadsafe(self.close_all_drivers(), self._loop)
            try:
                # 在同步上下文中，我们阻塞等待，直到驱动程序关闭
                future.result()
            except Exception as e:
                logging.error(f"❌ 关闭驱动时发生错误: {e}")

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join()
        logging.info("🔧 驱动工厂已关闭。")

    async def shutdown_async(self):
        """异步关闭所有驱动并停止后台事件循环。"""
        if not self._loop:
            return
        logging.info("🔧 正在关闭驱动工厂...")

        has_work = False
        with self._lock:
            if self._drivers or self._creation_futures:
                has_work = True

        if has_work:
            await self.close_all_drivers()

        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            # 在异步函数中，为了不阻塞事件循环，我们不能直接join
            # 但由于这是程序退出的最后一步，短暂的阻塞是可以接受的
            await asyncio.to_thread(self._thread.join)
        logging.info("🔧 驱动工厂已关闭。")

    async def close_all_drivers(self):
        """关闭所有由该工厂创建的 WebDriver 实例。"""
        # 取消任何仍在进行的创建任务
        with self._lock:
            futures_to_cancel = list(self._creation_futures.values())
            for future in futures_to_cancel:
                if not future.done():
                    future.cancel()
            self._creation_futures.clear()

        if futures_to_cancel:
            wrapped_futures = [asyncio.wrap_future(f) for f in futures_to_cancel]
            await asyncio.gather(*wrapped_futures, return_exceptions=True)

        # 关闭所有已创建的驱动
        drivers_to_close = []
        with self._lock:
            if not self._drivers:
                return
            logging.info("🔧 正在关闭所有 Selenium WebDriver 实例...")
            drivers_to_close = list(self._drivers.values())
            self._drivers.clear()

        close_tasks = [
            asyncio.to_thread(driver.quit) for driver in drivers_to_close
        ]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        logging.info("🔧 所有 Selenium 驱动已关闭。")

# 全局唯一的 DriverFactory 实例
driver_factory = DriverFactory()
