from dataclasses import dataclass


@dataclass(frozen=True)
class Verse:
    surah_number: int
    verse_number: int
    translation_text: str


@dataclass(frozen=True)
class Surah:
    number: int
    name: str
    verses: list[Verse]

    @property
    def formatted_filename(self) -> str:
        return f"{self.number:03d} - {self.name}.docx"

    @property
    def combined_translation(self) -> str:
        """Combines all verse translations with exactly one space between them."""
        return " ".join(v.translation_text for v in self.verses)