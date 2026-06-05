from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import TARGET_LANGUAGES, OUTPUT_MODES, AVAILABLE_PROVIDERS


def kb_after_upload() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Configurar opciones", callback_data="configure")
    builder.button(text="Ver capítulos", callback_data="list_chapters")
    builder.button(text="Traducir ahora", callback_data="translate_default")
    builder.adjust(1)
    return builder.as_markup()


def kb_languages() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, name in TARGET_LANGUAGES.items():
        builder.button(text=name, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


def kb_providers() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {"gemini": "Gemini 2.5 Flash (gratuito)", "deepseek": "DeepSeek Chat (economico)"}
    for provider in AVAILABLE_PROVIDERS:
        builder.button(text=labels.get(provider, provider), callback_data=f"provider:{provider}")
    builder.adjust(1)
    return builder.as_markup()


def kb_output_modes() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mode, label in OUTPUT_MODES.items():
        builder.button(text=label, callback_data=f"mode:{mode}")
    builder.adjust(1)
    return builder.as_markup()


def kb_confirm_translation() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirmar y traducir", callback_data="confirm_translate")
    builder.button(text="Cancelar", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def kb_quality_mode() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Normal (recomendado)", callback_data="quality:normal")
    builder.button(text="Alta calidad (doble costo)", callback_data="quality:high")
    builder.adjust(1)
    return builder.as_markup()
