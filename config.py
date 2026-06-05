import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

DEFAULT_TARGET_LANGUAGE: str = os.getenv("DEFAULT_TARGET_LANGUAGE", "es")
MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))

TRANSLATIONS_CACHE_DIR: Path = Path(os.getenv("TRANSLATIONS_CACHE_DIR", "translations_cache"))
DOWNLOADS_DIR: Path = Path(os.getenv("DOWNLOADS_DIR", "downloads"))

TRANSLATIONS_CACHE_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)

AVAILABLE_PROVIDERS: list[str] = []
if GEMINI_API_KEY:
    AVAILABLE_PROVIDERS.append("gemini")
if DEEPSEEK_API_KEY:
    AVAILABLE_PROVIDERS.append("deepseek")

TARGET_LANGUAGES: dict[str, str] = {
    "es": "Español",
    "en": "Inglés",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "pt": "Portugués",
    "ja": "Japonés",
    "zh": "Chino simplificado",
}

OUTPUT_MODES: dict[str, str] = {
    "replace": "Reemplazar original",
    "bilingual_inline": "Bilingüe en el mismo párrafo",
    "bilingual_block": "Bilingüe en párrafo separado",
}
