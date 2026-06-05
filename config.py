"""
Configuracion centralizada del sistema, cargada desde variables de entorno.

Todas las variables de entorno se leen aqui una sola vez al inicio, se validan,
y se exponen como constantes tipadas que el resto de los modulos importan directamente.
De esta manera ningun otro modulo necesita conocer los nombres de las variables de
entorno ni los valores por defecto, y cambiar la configuracion en produccion solo
requiere modificar el archivo .env sin tocar el codigo.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# load_dotenv lee el archivo .env del directorio de trabajo actual y carga las variables
# en el entorno del proceso. Si el archivo no existe (por ejemplo en produccion donde
# las variables se inyectan directamente), la funcion retorna sin error, de manera que
# el sistema funciona igualmente en ambos casos.
load_dotenv()

# TELEGRAM_BOT_TOKEN es la unica variable estrictamente obligatoria: sin ella el bot
# no puede conectarse a la API de Telegram y el sistema no tiene razon de existir.
# Se usa os.environ["KEY"] en lugar de os.getenv("KEY") precisamente para que Python
# lance un KeyError inmediatamente al arrancar si la variable no esta configurada,
# en lugar de fallar mas tarde con un error menos claro cuando se intenta usar el token.
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

# Las claves de los proveedores de traduccion son opcionales individualmente: el sistema
# puede funcionar con solo Gemini, solo DeepSeek, o con ambos. El string vacio como
# valor por defecto permite la verificacion booleana simple (if GEMINI_API_KEY:) que
# se usa mas adelante para construir la lista de proveedores disponibles.
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

DEFAULT_TARGET_LANGUAGE: str = os.getenv("DEFAULT_TARGET_LANGUAGE", "es")
MAX_CONCURRENT_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))

# Los directorios de trabajo se crean al arrancar si no existen. Esto evita que el bot
# falle en el primer uso con un FileNotFoundError en lugar de un error de configuracion,
# y simplifica el despliegue en servidores nuevos donde no es necesario crear manualmente
# la estructura de directorios antes de iniciar el servicio.
TRANSLATIONS_CACHE_DIR: Path = Path(os.getenv("TRANSLATIONS_CACHE_DIR", "translations_cache"))
DOWNLOADS_DIR: Path = Path(os.getenv("DOWNLOADS_DIR", "downloads"))

TRANSLATIONS_CACHE_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR.mkdir(exist_ok=True)

# La lista de proveedores disponibles se construye dinamicamente segun las claves
# configuradas, de forma que el bot solo le ofrezca al usuario las opciones que
# realmente funcionaran. El orden de la lista determina cual es el proveedor por
# defecto cuando el usuario elige traducir sin configurar opciones.
AVAILABLE_PROVIDERS: list[str] = []
if GEMINI_API_KEY:
    AVAILABLE_PROVIDERS.append("gemini")
if DEEPSEEK_API_KEY:
    AVAILABLE_PROVIDERS.append("deepseek")

# Los codigos de idioma siguen el estandar BCP 47, que es el mismo que usan los
# metadatos dc:language del OPF. De esta manera el codigo seleccionado por el usuario
# puede escribirse directamente en los metadatos del EPUB de salida sin conversion.
TARGET_LANGUAGES: dict[str, str] = {
    "es": "Español",
    "en": "Inglés",
    "fr": "Francés",
    "de": "Alemán",
    "it": "Italiano",
    "pt": "Portugués",
    "ja": "Japonés",
    "zh": "Chino simplificado",
}

# Los tres modos de salida definen como se combina la traduccion con el texto original
# en el HTML de cada capitulo. La capa de traduccion (Fase 4) es la que implementa
# la logica de cada modo; aqui solo se definen los identificadores y las etiquetas
# que el bot muestra al usuario en el teclado de configuracion.
OUTPUT_MODES: dict[str, str] = {
    "replace": "Reemplazar original",
    "bilingual_inline": "Bilingüe en el mismo párrafo",
    "bilingual_block": "Bilingüe en párrafo separado",
}
