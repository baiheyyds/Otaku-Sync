# clients/base_client.py
import httpx
from utils import logger

class BaseClient:
    """为所有API客户端提供通用功能的基类。"""
    STAFF_MAPPING = {
        "シナリオ": "剧本",
        "原画": "原画",
        "イラスト": "原画",  # Dlsite
        "声優": "声优",
        "音楽": "音乐",
    }

    def __init__(self, client: httpx.AsyncClient, base_url: str = ""):
        if not isinstance(client, httpx.AsyncClient):
            raise TypeError("A valid httpx.AsyncClient instance is required.")
        self.client = client
        self.base_url = base_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response | None:
        """
        通用的异步请求方法，包含日志记录和错误处理。
        """
        try:
            # 确保URL是绝对路径
            full_url = url if url.startswith("http") else f"{self.base_url}{url}"
            
            # 合并默认headers和调用时传入的headers
            request_headers = self.headers.copy()
            if "headers" in kwargs:
                request_headers.update(kwargs.pop("headers"))

            logger.info(f"[{self.__class__.__name__}] {method.upper()} {full_url}")
            
            response = await self.client.request(method, full_url, headers=request_headers, **kwargs)
            response.raise_for_status()
            
            logger.success(f"[{self.__class__.__name__}] 请求成功: {response.status_code} {response.reason_phrase}")
            return response
            
        except httpx.HTTPStatusError as e:
            logger.error(f"[{self.__class__.__name__}] 请求失败: {e.response.status_code} for url: {e.request.url}")
            logger.error(f"    -> 响应: {e.response.text[:300]}") # 打印部分响应内容
            return None
        except httpx.RequestError as e:
            logger.error(f"[{self.__class__.__name__}] 网络请求异常: {e.__class__.__name__} for url: {e.request.url}")
            return None
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}] 未知错误: {e}")
            return None

    async def get(self, url: str, **kwargs) -> httpx.Response | None:
        return await self._request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response | None:
        return await self._request("POST", url, **kwargs)

