# utils/driver.py
import os
import subprocess
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# 定义驱动程序缓存路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
driver_path = os.path.join(project_root, ".drivers")
os.environ['WDM_LOCAL'] = driver_path  # 设置webdriver-manager的下载路径

def prepare_driver_executable() -> str:
    """
    检查、下载并返回 ChromeDriver 的可执行文件路径。
    这是一个阻塞IO操作，且应该串行执行以避免 webdriver-manager 的并发问题。
    """
    try:
        logging.info("🔧 [WebDriver] 正在检查并准备 ChromeDriver...")
        executable_path = ChromeDriverManager().install()
        logging.info(f"✅ [WebDriver] ChromeDriver 已就绪，路径: {executable_path}")
        return executable_path
    except Exception as e:
        logging.error(f"❌ [WebDriver] 准备 ChromeDriver 时发生严重错误: {e}")
        raise

def create_driver_instance(executable_path: str):
    """
    使用给定的可执行文件路径创建一个 WebDriver 实例。
    这个过程可以安全地并行执行。
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    # 彻底屏蔽日志的关键
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(
        executable_path,
        log_output=subprocess.DEVNULL,
        # 在 Windows 上，这个标志位可以防止弹出黑色的 cmd 窗口
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1280, 800)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver
