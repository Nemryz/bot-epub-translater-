"""
Definicion de todos los teclados inline del bot.

Centralizar la construccion de teclados en un solo modulo tiene dos ventajas principales:
evita duplicar la logica de creacion en cada handler, y permite cambiar el texto o la
distribucion de los botones sin necesidad de buscar en multiples archivos. Los handlers
solo importan las funciones que necesitan, sin conocer los detalles internos de cada teclado.
"""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import TARGET_LANGUAGES, OUTPUT_MODES, AVAILABLE_PROVIDERS


def kb_after_upload() -> InlineKeyboardMarkup:
    """
    Teclado que aparece inmediatamente despues de que el usuario sube un archivo.

    Ofrece tres caminos: configurar opciones (idioma, proveedor, modo, calidad),
    ver la lista de capitulos con estimaciones de tiempo y costo, o traducir
    directamente con la configuracion por defecto para usuarios que no quieren
    pasar por el flujo de configuracion completo.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Configurar opciones", callback_data="configure")
    builder.button(text="Ver capítulos", callback_data="list_chapters")
    builder.button(text="Traducir ahora", callback_data="translate_default")
    builder.adjust(1)
    return builder.as_markup()


def kb_languages() -> InlineKeyboardMarkup:
    """
    Teclado de seleccion de idioma de destino.

    Se construye dinamicamente desde TARGET_LANGUAGES en config.py, de forma que
    agregar un nuevo idioma al sistema solo requiere agregar una entrada en ese
    diccionario y el teclado se actualiza automaticamente sin modificar este modulo.
    Los botones se distribuyen en dos columnas para aprovechar mejor el espacio.
    """
    builder = InlineKeyboardBuilder()
    for code, name in TARGET_LANGUAGES.items():
        builder.button(text=name, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


def kb_providers() -> InlineKeyboardMarkup:
    """
    Teclado de seleccion de proveedor de traduccion.

    Solo incluye los proveedores que tienen una clave de API configurada, segun
    la lista AVAILABLE_PROVIDERS que config.py construye al arrancar. De esta
    manera el usuario nunca ve un boton que llevaria a un error por falta de credenciales.
    """
    builder = InlineKeyboardBuilder()
    labels = {
        "gemini": "Gemini 2.5 Flash (gratuito)",
        "deepseek": "DeepSeek Chat (economico)",
    }
    for provider in AVAILABLE_PROVIDERS:
        builder.button(text=labels.get(provider, provider), callback_data=f"provider:{provider}")
    builder.adjust(1)
    return builder.as_markup()


def kb_output_modes() -> InlineKeyboardMarkup:
    """
    Teclado de seleccion del modo de salida del libro traducido.

    Se construye desde OUTPUT_MODES en config.py, siguiendo el mismo patron que
    kb_languages para mantener la coherencia del sistema y facilitar la incorporacion
    de nuevos modos en el futuro sin modificar este modulo.
    """
    builder = InlineKeyboardBuilder()
    for mode, label in OUTPUT_MODES.items():
        builder.button(text=label, callback_data=f"mode:{mode}")
    builder.adjust(1)
    return builder.as_markup()


def kb_confirm_translation() -> InlineKeyboardMarkup:
    """
    Teclado de confirmacion final antes de iniciar la traduccion.

    El boton de cancelar es importante aqui porque el usuario ya vio el resumen
    de su configuracion y puede arrepentirse antes de comprometer el proceso,
    que en libros largos puede tardar varios minutos y consumir tokens de la API.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirmar y traducir", callback_data="confirm_translate")
    builder.button(text="Cancelar", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def kb_quality_mode() -> InlineKeyboardMarkup:
    """
    Teclado de seleccion del nivel de calidad de la traduccion.

    El texto del boton de alta calidad menciona explicitamente el costo doble para
    que el usuario tome la decision con informacion completa, sin sorpresas al ver
    el consumo de tokens al final del proceso.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="Normal (recomendado)", callback_data="quality:normal")
    builder.button(text="Alta calidad (doble costo)", callback_data="quality:high")
    builder.adjust(1)
    return builder.as_markup()
