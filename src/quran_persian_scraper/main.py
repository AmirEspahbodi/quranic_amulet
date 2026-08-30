import sys
import asyncio
import logging
from src.quran_persian_scraper.config import ScraperConfig
from src.quran_persian_scraper.browser import BrowserManager
from src.quran_persian_scraper.scraper import QuranScraper


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("scraper.log", encoding="utf-8"),
        ],
    )


async def main() -> None:
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting Quran Persian Translation Scraper...")

    config = ScraperConfig()
    browser_mgr = BrowserManager(config)

    try:
        async with browser_mgr.create_page() as page:
            scraper = QuranScraper(page, config)
            await scraper.run()
    except Exception as e:
        logger.critical("Fatal error during crawling execution: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())