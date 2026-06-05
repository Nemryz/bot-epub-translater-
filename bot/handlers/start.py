from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

router = Router()

WELCOME = (
    "Hola, soy el bot de traduccion de libros electronicos.\n\n"
    "Envíame un archivo en cualquiera de estos formatos y lo traduzco al idioma que elijas:\n"
    "EPUB, MOBI, AZW3, FB2, RTF, DOCX\n\n"
    "Proveedores disponibles: Gemini 2.5 Flash y DeepSeek Chat.\n"
    "El archivo traducido conserva la estructura original del libro."
)

HELP = (
    "Como usar el bot:\n\n"
    "1. Envia el archivo del libro.\n"
    "2. Elige si configurar opciones o traducir directamente.\n"
    "3. Si configuras: selecciona idioma, proveedor, modo de salida y nivel de calidad.\n"
    "4. Confirma y espera el resultado.\n\n"
    "Modos de salida:\n"
    "  Reemplazar: solo queda la traduccion.\n"
    "  Bilingüe inline: traduccion junto al original en el mismo parrafo.\n"
    "  Bilingüe bloque: traduccion en parrafo separado debajo del original.\n\n"
    "Calidad alta: aplica una segunda pasada de revision que mejora la precision "
    "pero consume el doble de tokens."
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Operacion cancelada. Envia un archivo para comenzar de nuevo.")
