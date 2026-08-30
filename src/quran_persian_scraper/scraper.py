import logging
from playwright.async_api import Page
from src.quran_persian_scraper.config import ScraperConfig
from src.quran_persian_scraper.models import Surah
from src.quran_persian_scraper.translation_manager import TranslationManager
from src.quran_persian_scraper.verse_extractor import VerseExtractor
from src.quran_persian_scraper.docx_writer import DocxWriter

logger = logging.getLogger(__name__)


class QuranScraper:
    """Orchestrates navigation, translation setup, verse extraction, and file output."""

    def __init__(self, page: Page, config: ScraperConfig) -> None:
        self._page = page
        self._config = config
        self._translation_mgr = TranslationManager(page)
        self._verse_extractor = VerseExtractor(page, config.scroll_delay_ms)
        self._docx_writer = DocxWriter(config.output_dir)

    async def run(self) -> None:
        """Executes the crawl across all 114 surahs."""
        logger.info("Navigating to start page: %s", self._config.start_url)
        await self._page.goto(self._config.start_url, wait_until="domcontentloaded", timeout=self._config.timeout_ms)
        await self._page.wait_for_timeout(1000)

        for surah_idx in range(1, self._config.total_surahs + 1):
            logger.info("==========================================")
            logger.info("Processing Surah %d / %d", surah_idx, self._config.total_surahs)
            logger.info("==========================================")

            # Step 1: Ensure IslamHouse.com translation is selected
            await self._translation_mgr.ensure_islamhouse_translation()

            # Step 2: Extract Surah Name from the page header
            surah_name = await self._verse_extractor.extract_surah_name()
            logger.info("Surah Identified: %03d - %s", surah_idx, surah_name)

            # Step 3: Scroll through all verses and extract translations
            verses = await self._verse_extractor.scroll_and_collect_verses(surah_idx)

            # Step 4: Write to DOCX
            surah = Surah(number=surah_idx, name=surah_name, verses=verses)
            self._docx_writer.save_surah(surah)

            # Step 5: Proceed to the next surah via 'Continue Reading' (ادامه مطلب)
            if surah_idx < self._config.total_surahs:
                await self._navigate_to_next_surah()

        logger.info("All 114 Surahs successfully extracted and saved.")

    async def _navigate_to_next_surah(self) -> None:
        """Finds and clicks 'ادامه مطلب' (Continue Reading) to advance to the next surah."""
        await self._page.wait_for_timeout(10000)

        # Wait for next surah to load
        await self._page.wait_for_load_state("domcontentloaded")
        await self._page.wait_for_timeout(1200)
    
        await self._page.evaluate("window.scrollBy(0, window.innerHeight * 0.85);")
        await self._page.wait_for_timeout(250)

        # 4. Scroll to bottom and click "ادامه مطلب"
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await self._page.wait_for_timeout(300)

        next_button = self._page.locator(
            "a:has-text('ادامه مطلب'), button:has-text('ادامه مطلب'), [aria-label*='ادامه مطلب']"
        ).first
        
        logger.info("Clicking 'ادامه مطلب' (Continue Reading)...")
        await next_button.scroll_into_view_if_needed(timeout=120_000)
        await next_button.wait_for(state="visible", timeout=120_000)
        await next_button.click()
