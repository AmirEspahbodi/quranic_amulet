import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from src.quran_persian_scraper.config import ScraperConfig

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages the lifecycle of the Chrome browser instance and context."""

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config

    @asynccontextmanager
    async def create_page(self) -> AsyncGenerator[Page, None]:
        async with async_playwright() as pw:
            chrome_path = self._config.get_chrome_executable()
            launch_kwargs = {
                "headless": self._config.headless,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--window-size=1920,1080",
                    "--start-maximized",
                ],
            }

            if chrome_path:
                logger.info("Using system Google Chrome binary at: %s", chrome_path)
                launch_kwargs["executable_path"] = chrome_path
            else:
                launch_kwargs["channel"] = "chrome"

            browser: Browser = await pw.chromium.launch(**launch_kwargs)
            context: BrowserContext = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="fa-IR",
            )

            page: Page = await context.new_page()

            try:
                yield page
            finally:
                await context.close()
                await browser.close()