"""
Handler de recepcion de archivos y definicion del estado FSM de la sesion.

Este modulo tiene dos responsabilidades que van juntas: define TranslationSession,
que es la maquina de estados que rastrea en que paso del flujo se encuentra cada
usuario, y maneja el evento de recibir un documento, que es el punto de entrada
de todo el proceso de traduccion. Separar estas responsabilidades en dos modulos
distintos causaria una dependencia circular, ya que settings.py necesita importar
TranslationSession para filtrar callbacks por estado.
"""

import uuid
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message, Document
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiofiles
import config
from bot.keyboards import kb_after_upload

router = Router()

# Los formatos aceptados son los que Calibre puede convertir a EPUB, ademas del EPUB
# mismo. Los archivos en otros formatos se rechazan con un mensaje claro antes de
# intentar descargarlos, lo cual ahorra ancho de banda y evita errores tardios.
ACCEPTED_EXTENSIONS = {".epub", ".mobi", ".azw3", ".fb2", ".rtf", ".docx"}


class TranslationSession(StatesGroup):
    """
    Maquina de estados que rastrea el progreso de cada usuario en el flujo de traduccion.

    Cada estado corresponde a un paso del flujo: la recepcion del archivo, los pasos
    de configuracion, la confirmacion y la traduccion activa. aiogram usa estos estados
    para filtrar mensajes y callbacks, de manera que un boton de seleccion de idioma
    solo responde si el usuario esta en el estado selecting_language, evitando que
    interacciones fuera de orden corrompan la sesion.
    """

    waiting_for_file = State()
    configuring = State()
    selecting_language = State()
    selecting_provider = State()
    selecting_mode = State()
    selecting_quality = State()
    confirming = State()
    translating = State()


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext) -> None:
    """
    Recibe un documento enviado por el usuario, lo descarga y prepara la sesion.

    La descarga se hace con aiofiles para no bloquear el event loop del bot mientras
    se escribe el archivo en disco, lo que es importante porque Telegram puede enviar
    archivos de varios megabytes y una escritura sincrona congela el bot para todos
    los usuarios mientras dura. El archivo se guarda en un subdirectorio unico por
    sesion (usando uuid4) para que multiples usuarios puedan subir archivos al mismo
    tiempo sin que sus descargas se sobreescriban entre si.
    """
    document: Document = message.document
    filename = document.file_name or "libro"
    extension = Path(filename).suffix.lower()

    if extension not in ACCEPTED_EXTENSIONS:
        await message.answer(
            f"El formato {extension or 'desconocido'} no es compatible.\n"
            f"Formatos aceptados: {', '.join(sorted(ACCEPTED_EXTENSIONS))}"
        )
        return

    job_id = uuid.uuid4().hex
    job_dir = config.DOWNLOADS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    local_path = job_dir / filename

    await message.answer("Descargando archivo...")

    file = await message.bot.get_file(document.file_id)
    downloaded = await message.bot.download_file(file.file_path)

    async with aiofiles.open(local_path, "wb") as f:
        await f.write(downloaded.read())

    # El estado inicial de la sesion incluye los valores por defecto para todas las
    # opciones de configuracion, de manera que si el usuario elige "Traducir ahora"
    # sin pasar por el flujo de configuracion, el sistema tenga valores validos
    # para todas las variables que el proceso de traduccion necesita.
    await state.update_data(
        job_id=job_id,
        job_dir=str(job_dir),
        original_path=str(local_path),
        original_extension=extension,
        filename=filename,
        target_language=config.DEFAULT_TARGET_LANGUAGE,
        provider=config.AVAILABLE_PROVIDERS[0] if config.AVAILABLE_PROVIDERS else None,
        output_mode="replace",
        quality_mode="normal",
    )
    await state.set_state(TranslationSession.waiting_for_file)

    await message.answer(
        f"Archivo recibido: {filename}\n"
        f"Formato: {extension.lstrip('.')}\n\n"
        "Como quieres continuar?",
        reply_markup=kb_after_upload(),
    )
