import logging
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class TranslationManager:
    """Handles the selection of the IslamHouse.com Persian translation and deselects others."""

    def __init__(self, page: Page) -> None:
        self._page = page

    async def ensure_islamhouse_translation(self) -> None:
        """
        1. Clicks the translation selector box.
        2. In the Persian section, deselects any other translation.
        3. Selects IslamHouse.com.
        4. Closes the translation drawer via the 'X' button.
        """
        # Check if IslamHouse.com is already the active translation
        banner_btn = self._page.locator('span[class*="ReadingModeActions_translationText"]').first
        if await banner_btn.count() > 0:
            btn_text = await banner_btn.inner_text()
            if "IslamHouse.com" in btn_text:
                logger.info("IslamHouse.com translation is already active.")
                return

        logger.info("Opening translation selection drawer...")
        await banner_btn.click()
        await self._page.wait_for_timeout(10_000)

        # Locate the translations drawer / modal
        drawer = self._page.locator("[role='dialog'], [data-testid='translations-drawer'], aside, div").filter(
            has_text="ترجمه ها"
        ).first

        # 1. Unselect "Hussein Taji Kal Dari" if currently selected
        hussein_checkbox = drawer.locator('[data-testid="translation-option-29"] button[role="checkbox"]')
        if await hussein_checkbox.get_attribute("aria-checked") == "true":
            await hussein_checkbox.click()

        # 2. Select "IslamHouse.com" if currently unselected
        islamhouse_checkbox = drawer.locator('[data-testid="translation-option-135"] button[role="checkbox"]')
        if await islamhouse_checkbox.get_attribute("aria-checked") == "false":
            await islamhouse_checkbox.click()
            
        # Close the drawer by clicking the close 'X' button
        # Close the translation/settings drawer directly
        await drawer.get_by_test_id("settings-drawer").get_by_test_id("drawer-close-button").click()
        await self._page.wait_for_timeout(500)