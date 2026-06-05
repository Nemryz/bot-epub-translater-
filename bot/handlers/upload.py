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

ACCEPTED_EXTENSIONS = {".epub", ".mobi", ".azw3", ".fb2", ".rtf", ".docx"}


class TranslationSession(StatesGroup):
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
