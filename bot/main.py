"""
Punto de entrada del bot: construye el Dispatcher, registra los routers y arranca el polling.

No contiene logica de negocio, que vive enteramente en los handlers. La separacion
es deliberada: si en el futuro se cambia de polling a webhooks, o si se quiere
agregar middleware de logging o autenticacion, solo este archivo necesita modificarse
sin tocar ninguna otra parte del sistema.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
import config
from bot.handlers import upload, settings, start
from state.sqlite_storage import SqliteStorage

# El formato de logging incluye timestamp, nivel, nombre del logger y mensaje, lo cual
# es suficiente para depurar problemas en produccion sin necesidad de configurar un
# sistema de logging mas elaborado como structlog. El nivel INFO muestra el inicio
# del bot y las peticiones procesadas, sin el ruido de DEBUG que incluye el trafico
# interno de la conexion websocket con los servidores de Telegram.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# set_commands registra los comandos del bot en la API de Telegram, lo que hace que
# aparezcan en el menu desplegable cuando el usuario escribe "/" en el chat. Esto es
# puramente cosmético desde el punto de vista del bot (los comandos funcionan aunque
# no esten registrados), pero mejora significativamente la experiencia del usuario
# en clientes de Telegram que muestran ese menu de ayuda.
async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Iniciar el bot"),
        BotCommand(command="help", description="Mostrar ayuda"),
        BotCommand(command="cancel", description="Cancelar la operacion actual"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    # SqliteStorage persiste el estado FSM en disco, de manera que si el bot se
    # reinicia en medio de un flujo de configuracion el usuario puede retomarlo
    # sin necesidad de volver a subir el archivo. La base de datos se guarda en
    # TRANSLATIONS_CACHE_DIR junto con el resto de los archivos de estado del sistema.
    # Si en el futuro el bot necesita escalar a multiples instancias se reemplaza
    # por RedisStorage sin cambiar ningun handler, porque aiogram abstrae el
    # almacenamiento detras de una interfaz comun con los mismos metodos.
    storage = SqliteStorage(config.TRANSLATIONS_CACHE_DIR / "bot_state.db")
    dp = Dispatcher(storage=storage)

    # El orden de registro de los routers importa: aiogram los evalua en secuencia y
    # el primer router cuyo filtro coincide con un mensaje o callback es el que lo procesa.
    # start debe ir primero porque sus comandos (/start, /cancel) deben tener prioridad
    # sobre cualquier otro handler, incluyendo el handler generico de documentos de upload.
    dp.include_router(start.router)
    dp.include_router(upload.router)
    dp.include_router(settings.router)

    await set_commands(bot)

    logger.info("Bot iniciado. Esperando mensajes...")

    # skip_updates=True descarta los mensajes que llegaron mientras el bot estaba
    # apagado. Sin esto, al reiniciar el bot procesaria todos los archivos que los
    # usuarios enviaron durante la caida, lo cual en la mayoria de los casos produce
    # errores porque los jobs y el estado FSM no existen en el nuevo proceso.
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
