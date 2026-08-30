import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScraperConfig:
    start_url: str = "https://quran.com/fa/al-fatihah"
    base_url: str = "https://quran.com"
    output_dir: Path = Path("surah_docx_output")
    total_surahs: int = 114
    timeout_ms: int = 100_000
    scroll_delay_ms: int = 3_000
    headless: bool = False  # Set to True for headless servers

    @staticmethod
    def get_chrome_executable() -> str | None:
        """Finds google-chrome-stable executable on Linux systems."""
        candidates = [
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome",
            "/opt/google/chrome/google-chrome",
            shutil.which("google-chrome-stable"),
            shutil.which("google-chrome"),
        ]
        for path in candidates:
            if path and os.path.exists(path) and os.access(path, os.X_OK):
                return path
        return None