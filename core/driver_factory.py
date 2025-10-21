# core/driver_factory.py
import asyncio
import logging
import threading
from concurrent.futures import Future
from typing import Dict, List, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from utils.driver import create_driver_instance, prepare_driver_executable


class DriverFactory:
    """管理 Selenium WebDriver 实例的创建和销毁，并在专用线程中运行asyncio事件循环。"""

    def __init__(self):
        self._drivers: Dict[str, WebDriver] = {}
        self._creation_futures: Dict[str, Future] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # 用于保护共享状态的线程锁
        self._loop_started = threading.Event()

    def _run_loop(self):
        """在后台线程中运行asyncio事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_started.set()
        self._loop.run_forever()

    def start(self):
        """启动后台线程和事件循环，并等待其准备就绪。"""
        with self._lock:
            if self._thread is None:
                logging.info("🔧 正在启动驱动工厂的后台事件循环线程...")
                self._thread = threading.Thread(target=self._run_loop, daemon=True)
                self._thread.start()
                self._loop_started.wait()
                logging.info("🔧 驱动工厂后台线程已准备就绪。")

    async def _prepare_and_create_drivers_async(self, driver_keys: List[str]):
        """
        在后台事件循环中，先串行准备驱动文件，然后并行实例化驱动。
        这是实现安全并行创建的核心逻辑。
        """
        # 阶段1: 在后台事件循环中串行准备驱动文件
        logging.info(f"🚀 [后台] 开始串行准备 {driver_keys} 的驱动文件...")
        driver_paths = {}
        for key in driver_keys:
            try:
                # prepare_driver_executable 是阻塞的，用 to_thread 运行
                path = await asyncio.to_thread(prepare_driver_executable)
                driver_paths[key] = path
            except Exception as e:
                logging.error(f"❌ [后台] 准备 {key} 的驱动文件失败，中止创建过程: {e}")
                # 将异常存入 future，以便 get_driver 可以捕获
                with self._lock:
                    future = self._creation_futures.get(key)
                    if future and not future.done():
                        future.set_exception(e)
                return # 准备失败，则不继续

        logging.info("✅ [后台] 所有驱动文件已准备就绪。")

        # 阶段2: 在后台事件循环中并行实例化驱动
        logging.info(f"🚀 [后台] 开始并行实例化 {driver_keys}...")

        async def create_instance_task(key: str, path: str):
            try:
                driver = await asyncio.to_thread(create_driver_instance, path)
                with self._lock:
                    self._drivers[key] = driver
                logging.info(f"✅ [后台] {key} 已成功实例化。")
            except Exception as e:
                logging.error(f"❌ [后台] 实例化 {key} 失败: {e}")
                # 再次将异常存入 future
                with self._lock:
                    future = self._creation_futures.get(key)
                    if future and not future.done():
                        future.set_exception(e)

        tasks = [create_instance_task(key, path) for key, path in driver_paths.items()]
        await asyncio.gather(*tasks)
        logging.info("✅ [后台] 所有驱动实例化任务已完成。")


    def start_background_creation(self, driver_keys: list[str]):
        """为指定的驱动程序启动一个统一的后台创建任务。"""
        self.start()

        keys_to_create = []
        with self._lock:
            for key in driver_keys:
                if key not in self._drivers and key not in self._creation_futures:
                    keys_to_create.append(key)

        if not keys_to_create:
            return

        logging.info(f"🔧 提交 {keys_to_create} 的后台创建任务...")
        assert self._loop is not None
        # 创建一个统一的 future 来代表整个创建过程
        future = asyncio.run_coroutine_threadsafe(
            self._prepare_and_create_drivers_async(keys_to_create), self._loop
        )
        # 让所有相关的 key 都共享这个 future
        with self._lock:
            for key in keys_to_create:
                self._creation_futures[key] = future

    async def get_driver(self, driver_key: str) -> Optional[WebDriver]:
        """
        获取一个驱动实例。
        如果实例已创建，则直接返回。
        如果正在创建中，则等待创建完成。
        """
        future = None
        with self._lock:
            if driver_key in self._drivers:
                return self._drivers[driver_key]
            future = self._creation_futures.get(driver_key)

        if future:
            logging.info(f"🔧 正在等待 {driver_key} 的后台任务完成...")
            try:
                # 等待整个批次的 future 完成
                await asyncio.wrap_future(future)
                # future 完成后，驱动应该已经在 self._drivers 中了
                with self._lock:
                    if driver_key in self._drivers:
                        logging.info(f"✅ {driver_key} 已获取。")
                        return self._drivers[driver_key]
                    else:
                        # 如果驱动不在，说明在后台创建过程中失败了
                        logging.error(f"❌ 任务完成但 {driver_key} 未被成功创建 (详见后台日志)。")
                        return None
            except Exception as e:
                logging.error(f"❌ 等待 {driver_key} 创建时发生错误: {e}")
                return None
            finally:
                # 无论成功与否，都清理掉 future
                with self._lock:
                    self._creation_futures.pop(driver_key, None)


        logging.warning(f"⚠️ {driver_key} 既未创建也无创建任务。")
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
            await asyncio.to_thread(self._thread.join)
        logging.info("🔧 驱动工厂已关闭。")

    async def close_all_drivers(self):
        """关闭所有由该工厂创建的 WebDriver 实例。"""
        with self._lock:
            futures_to_cancel = list(self._creation_futures.values())
            for future in futures_to_cancel:
                if not future.done():
                    future.cancel()
            self._creation_futures.clear()

        if futures_to_cancel:
            wrapped_futures = [asyncio.wrap_future(f) for f in futures_to_cancel]
            await asyncio.gather(*wrapped_futures, return_exceptions=True)

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
