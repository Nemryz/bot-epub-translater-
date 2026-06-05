"""
Handlers del flujo de configuracion de la sesion de traduccion.

Este modulo gestiona la secuencia de cuatro pantallas de configuracion que el usuario
recorre antes de confirmar la traduccion: seleccion de idioma, de proveedor, de modo
de salida, y de nivel de calidad. Cada pantalla es un callback handler que actualiza
el estado FSM con la eleccion del usuario y muestra la siguiente pantalla. Al final
del flujo se muestra un resumen de toda la configuracion con un teclado de confirmacion.
"""

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
    """
    Inicia el flujo de configuracion mostrando el teclado de seleccion de idioma.

    Es el punto de entrada del flujo de cuatro pasos. Cambia el estado a
    selecting_language para que los siguientes callbacks de idioma sean procesados
    correctamente por el handler correspondiente.
    """
    await state.set_state(TranslationSession.selecting_language)
    await callback.message.edit_text(
        "Selecciona el idioma de destino:",
        reply_markup=kb_languages(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def select_language(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Guarda el idioma seleccionado y avanza al paso de seleccion de proveedor.

    Si no hay ningun proveedor configurado (ninguna clave de API en el .env), termina
    el flujo con un mensaje de error en lugar de mostrar un teclado de proveedores vacio,
    lo cual confundiria al usuario sin darle informacion util sobre como resolver el problema.
    """
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
    """Guarda el proveedor seleccionado y avanza al paso de seleccion de modo de salida."""
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
    """Guarda el modo de salida seleccionado y avanza al paso de seleccion de calidad."""
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
    """
    Guarda el nivel de calidad y muestra el resumen final de configuracion.

    El resumen incluye todas las opciones elegidas en los pasos anteriores, leidas
    desde el estado FSM para garantizar que lo que se muestra es exactamente lo que
    se va a usar, y no una reconstruccion que podria diferir si el usuario salto algun
    paso o si hubo algun problema al guardar una eleccion anterior.
    """
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
    """
    Muestra el resumen de configuracion por defecto y solicita confirmacion.

    Este handler responde al boton "Traducir ahora" que el usuario ve justo despues
    de subir el archivo, sin haber pasado por el flujo de configuracion. Los valores
    por defecto que se muestran son los mismos que se guardaron en el estado al recibir
    el archivo en upload.py, de manera que el resumen siempre es consistente con lo
    que realmente se usara.
    """
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
    """Cancela la sesion actual, limpia el estado FSM y notifica al usuario."""
    await state.clear()
    await callback.message.edit_text(
        "Operacion cancelada. Envia un archivo para comenzar de nuevo."
    )
    await callback.answer()
