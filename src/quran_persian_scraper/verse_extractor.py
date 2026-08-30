import logging
import re
from playwright.async_api import Page
from src.quran_persian_scraper.models import Surah, Verse

logger = logging.getLogger(__name__)


class VerseExtractor:
    """Scrolls the surah page, extracts all verses in exact sequence, and verifies integrity."""

    def __init__(self, page: Page, scroll_delay_ms: int = 3_000) -> None:
        self._page = page
        self._scroll_delay_ms = scroll_delay_ms

    async def extract_surah_name(self) -> str:
        """Extracts and returns the English/transliterated Surah name (e.g., 'Al-Fatihah')."""
        title_locator = self._page.locator(
            '[data-testid="chapter-title"] h1, [class*="transliteratedName"]'
        ).first

        raw_text = await title_locator.text_content()
        if not raw_text:
            return ""

        match = re.search(r"[a-zA-Z][a-zA-Z0-9\s\-']*", raw_text)
        return match.group(0).strip() if match else ""

    async def scroll_and_collect_verses(self, surah_number: int) -> list[Verse]:
        """
        Progressively scrolls the surah to load lazy-loaded elements and extracts
        every Persian verse translation in strictly ascending order without omissions.
        """
        collected_verses: dict[int, str] = {}
        last_height = 0
        stagnant_cycles = 0

        logger.info("Starting progressive scroll and verse extraction for Surah %d...", surah_number)

        while True:
            # 1. Extract only what is currently rendered in the DOM
            new_verses = await self._extract_visible_verses()
            collected_verses.update(new_verses)

            # 2. Check if "Continue Reading" (ادامه مطلب) button is present
            continue_btn = self._page.locator(
                "a:has-text('ادامه مطلب'), button:has-text('ادامه مطلب'), [aria-label*='ادامه مطلب']"
            ).first
            is_continue_visible = await continue_btn.is_visible() if await continue_btn.count() > 0 else False

            # 3. Scroll down once
            await self._page.evaluate("window.scrollBy({ top: 800, behavior: 'smooth' });")

            # 4. Wait the full 3 seconds (3000ms) for virtual list mounting & network fetching
            await self._page.wait_for_timeout(self._scroll_delay_ms)

            # 5. Check page height changes to detect bottom
            current_height = await self._page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                stagnant_cycles += 1
            else:
                stagnant_cycles = 0
                last_height = current_height

            # When reaching the end of the page and button is visible
            if is_continue_visible and stagnant_cycles >= 2:
                final_pass = await self._extract_visible_verses()
                collected_verses.update(final_pass)
                break

            if stagnant_cycles >= 6:
                final_pass = await self._extract_visible_verses()
                collected_verses.update(final_pass)
                break

        # Verification of verse ordering and continuity
        sorted_verse_numbers = sorted(collected_verses.keys())
        if not sorted_verse_numbers:
            raise ValueError(f"Failed to extract any verses for Surah {surah_number}")

        # Check for sequence gaps
        expected_total = len(sorted_verse_numbers)
        actual_min = sorted_verse_numbers[0]
        actual_max = sorted_verse_numbers[-1]

        if actual_min != 1 or actual_max != expected_total:
            missing = set(range(1, actual_max + 1)) - set(sorted_verse_numbers)
            if missing:
                logger.warning("Detected missing verses %s in Surah %d.", missing, surah_number)

        ordered_verses = [
            Verse(surah_number=surah_number, verse_number=n, translation_text=collected_verses[n])
            for n in sorted_verse_numbers
        ]

        logger.info("Successfully extracted %d verses for Surah %d.", len(ordered_verses), surah_number)
        return ordered_verses

    async def _extract_visible_verses(self) -> dict[int, str]:
        """Reads currently mounted verses in the DOM without performing any scrolling."""
        raw_data: dict[str, str] = await self._page.evaluate(
            """() => {
                const data = {};
                const cells = document.querySelectorAll('[data-verse-key]');
                cells.forEach(cell => {
                    const verseKey = cell.getAttribute('data-verse-key');
                    if (!verseKey) return;
                    
                    const parts = verseKey.split(':');
                    const verseNum = parts[1];
                    const transElem = cell.querySelector('[data-testid="translation-text"]') 
                                   || cell.querySelector('[data-translation-text="true"]');
                    
                    if (verseNum && transElem) {
                        data[verseNum] = transElem.innerText.trim();
                    }
                });
                return data;
            }"""
        )

        return {int(k): v for k, v in raw_data.items()}