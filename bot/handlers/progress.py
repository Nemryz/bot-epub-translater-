import time
import asyncio
from aiogram.types import Message

PROGRESS_BAR_WIDTH = 20
MIN_EDIT_INTERVAL = 1.2


class ProgressReporter:
    def __init__(self, message: Message, total_chapters: int) -> None:
        self._message = message
        self._total = total_chapters
        self._current = 0
        self._last_edit_at = 0.0
        self._lock = asyncio.Lock()

    async def update(self, completed_chapters: int) -> None:
        async with self._lock:
            self._current = completed_chapters
            now = time.monotonic()
            if now - self._last_edit_at < MIN_EDIT_INTERVAL:
                return
            self._last_edit_at = now
            await self._edit()

    async def done(self) -> None:
        self._current = self._total
        await self._edit()

    async def _edit(self) -> None:
        pct = int(self._current / self._total * 100) if self._total else 0
        filled = int(PROGRESS_BAR_WIDTH * self._current / self._total) if self._total else 0
        bar = "█" * filled + "░" * (PROGRESS_BAR_WIDTH - filled)
        text = (
            f"Traduciendo...\n"
            f"{bar} {pct}%\n"
            f"Capitulo {self._current} de {self._total}"
        )
        try:
            await self._message.edit_text(text)
        except Exception:
            pass
