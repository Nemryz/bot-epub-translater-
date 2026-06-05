import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
import config
from bot.handlers import upload, settings, start

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Iniciar el bot"),
        BotCommand(command="help", description="Mostrar ayuda"),
        BotCommand(command="cancel", description="Cancelar la operacion actual"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(upload.router)
    dp.include_router(settings.router)

    await set_commands(bot)

    logger.info("Bot iniciado. Esperando mensajes...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
