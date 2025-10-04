# core/cache_warmer.py
import asyncio
import httpx
# from utils import logger # No longer needed
from clients.notion_client import NotionClient
from clients.brand_cache import BrandCache
from config.config_token import NOTION_TOKEN, BRAND_DB_ID, GAME_DB_ID

async def warm_up_brand_cache_standalone():
    """
    A self-contained, silent function to warm up the brand cache.
    It creates its own clients to be run in a separate thread.
    It does not perform any logging to avoid cross-thread UI issues.
    """
    try:
        brand_cache = BrandCache()

        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(http2=True), timeout=60, follow_redirects=True) as client:
            notion_client = NotionClient(NOTION_TOKEN, GAME_DB_ID, BRAND_DB_ID, client)

            # The get_all_brands method is now also silent
            all_notion_brands = await notion_client.get_all_brands(silent=True)

            if not all_notion_brands:
                return

            for brand_details in all_notion_brands:
                brand_cache.add_brand(
                    name=brand_details["name"],
                    page_id=brand_details["page_id"],
                    has_icon=brand_details["has_icon"],
                )
            
            brand_cache.save_cache(silent=True) # This method also needs to be silent

    except Exception:
        # Silently fail. The main application will continue to work,
        # just without the pre-warmed cache.
        pass