from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.handlers.upload import TranslationSession
from bot.keyboards import (
    kb_languages,
    kb_providers,
    kb_output_modes,
    kb_quality_mode,
    kb_confirm_translation,
)
import config

router = Router()


@router.callback_query(F.data == "configure")
async def start_configure(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TranslationSession.selecting_language)
    await callback.message.edit_text(
        "Selecciona el idioma de destino:",
        reply_markup=kb_languages(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def select_language(callback: CallbackQuery, state: FSMContext) -> None:
    language = callback.data.split(":")[1]
    await state.update_data(target_language=language)
    await state.set_state(TranslationSession.selecting_provider)

    lang_name = config.TARGET_LANGUAGES.get(language, language)

    if not config.AVAILABLE_PROVIDERS:
        await callback.message.edit_text(
            "No hay proveedores configurados. Agrega al menos una clave de API en el archivo .env."
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Idioma seleccionado: {lang_name}\n\nSelecciona el proveedor de traduccion:",
        reply_markup=kb_providers(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("provider:"))
async def select_provider(callback: CallbackQuery, state: FSMContext) -> None:
    provider = callback.data.split(":")[1]
    await state.update_data(provider=provider)
    await state.set_state(TranslationSession.selecting_mode)
    await callback.message.edit_text(
        f"Proveedor seleccionado: {provider}\n\nSelecciona el modo de salida:",
        reply_markup=kb_output_modes(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mode:"))
async def select_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    await state.update_data(output_mode=mode)
    await state.set_state(TranslationSession.selecting_quality)
    mode_label = config.OUTPUT_MODES.get(mode, mode)
    await callback.message.edit_text(
        f"Modo de salida: {mode_label}\n\nSelecciona el nivel de calidad:",
        reply_markup=kb_quality_mode(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quality:"))
async def select_quality(callback: CallbackQuery, state: FSMContext) -> None:
    quality = callback.data.split(":")[1]
    await state.update_data(quality_mode=quality)
    await state.set_state(TranslationSession.confirming)

    data = await state.get_data()
    lang_name = config.TARGET_LANGUAGES.get(data["target_language"], data["target_language"])
    mode_label = config.OUTPUT_MODES.get(data["output_mode"], data["output_mode"])

    summary = (
        f"Configuracion lista:\n"
        f"  Idioma: {lang_name}\n"
        f"  Proveedor: {data['provider']}\n"
        f"  Modo: {mode_label}\n"
        f"  Calidad: {'alta (2 pasadas)' if quality == 'high' else 'normal'}\n\n"
        f"Listo para traducir?"
    )
    await callback.message.edit_text(summary, reply_markup=kb_confirm_translation())
    await callback.answer()


@router.callback_query(F.data == "translate_default")
async def translate_default(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TranslationSession.confirming)
    data = await state.get_data()
    lang_name = config.TARGET_LANGUAGES.get(data["target_language"], data["target_language"])

    summary = (
        f"Configuracion por defecto:\n"
        f"  Idioma: {lang_name}\n"
        f"  Proveedor: {data.get('provider', 'no configurado')}\n"
        f"  Modo: reemplazar\n\n"
        f"Listo para traducir?"
    )
    await callback.message.edit_text(summary, reply_markup=kb_confirm_translation())
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Operacion cancelada. Envia un archivo para comenzar de nuevo.")
    await callback.answer()
