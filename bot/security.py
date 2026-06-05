"""
Funciones de seguridad centralizadas para la validacion de entradas y archivos del bot.

Este modulo agrupa todas las comprobaciones de seguridad en un solo lugar para que
cualquier modificacion en las reglas de validacion se propague a todos los handlers
que las usan sin necesidad de buscarlas y cambiarlas en multiples archivos. Las
funciones no tienen efectos secundarios ni estado: reciben datos, comprueban condiciones,
y lanzan ValueError con un mensaje explicativo si algo no cumple los requisitos, o
devuelven True si todo esta correcto. Los handlers son responsables de capturar esos
errores y convertirlos en respuestas apropiadas para el usuario.
"""

import logging
import re
from pathlib import PurePosixPath

import config

logger = logging.getLogger(__name__)

# Los patrones que indican un intento de prompt injection son frases que intentan
# anular las instrucciones del sistema del LLM. Para un bot de traduccion personal
# el riesgo es bajo, pero en un escenario de uso compartido donde distintos usuarios
# pueden subir EPUBs, un archivo malicioso podria intentar manipular al modelo para
# que ignore el sistema prompt y ejecute instrucciones del atacante.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+your\s+(previous\s+)?(instructions|training)", re.IGNORECASE),
    re.compile(r"(disregard|bypass|override)\s+(all\s+)?instructions", re.IGNORECASE),
    re.compile(r"new\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+\w+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an)\s+\w+\s+without\s+restrictions", re.IGNORECASE),
]


def is_authorized(user_id: int) -> bool:
    """
    Verifica si un usuario tiene permiso para usar el bot.

    Si la lista ALLOWED_USER_IDS en config esta vacia, cualquier usuario puede
    usar el bot, lo que es apropiado para uso personal donde el token del bot
    no esta expuesto publicamente. Si la lista tiene al menos un ID, solo esos
    usuarios pueden iniciar traducciones, lo que permite compartir el bot con un
    grupo cerrado sin abrirlo al publico general.
    """
    if not config.ALLOWED_USER_IDS:
        return True
    return user_id in config.ALLOWED_USER_IDS


def check_file_size(size_bytes: int) -> None:
    """
    Lanza ValueError si el archivo supera el tamaño maximo permitido configurado
    en MAX_FILE_SIZE_MB. La verificacion se hace antes de iniciar la descarga del
    archivo usando el campo file_size del objeto Document de Telegram, que contiene
    el tamaño declarado por el cliente del usuario, de manera que no se consume
    ancho de banda descargando archivos que de todas formas seran rechazados.
    """
    max_bytes = config.MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(
            f"El archivo supera el tamaño maximo permitido de {config.MAX_FILE_SIZE_MB} MB. "
            f"Tamaño recibido: {size_bytes / (1024 * 1024):.1f} MB."
        )


def validate_filename(filename: str) -> None:
    """
    Verifica que el nombre del archivo sea seguro para usarlo como nombre de archivo
    en disco, rechazando nombres que contengan componentes de ruta, caracteres nulos,
    o longitudes excesivas que podrian provocar errores al crear el archivo en el
    directorio de descargas.
    """
    if not filename or not filename.strip():
        raise ValueError("El nombre del archivo no puede estar vacio.")
    if len(filename) > 200:
        raise ValueError("El nombre del archivo supera los 200 caracteres permitidos.")
    # Caracteres que permiten inyectar componentes de ruta o caracteres de control.
    if any(c in filename for c in ("/", "\\", "..", "\0", "\r", "\n")):
        raise ValueError(
            "El nombre del archivo contiene caracteres no permitidos. "
            "Renombra el archivo y vuelve a enviarlo."
        )


def validate_zip_entry_path(zip_path: str) -> None:
    """
    Verifica que la ruta de un entry dentro del ZIP del EPUB no intente escapar
    del directorio raiz del archivo, un ataque conocido como zip slip. Un EPUB
    malicioso podria declarar en su manifest hrefs como ../../etc/passwd para
    intentar leer o sobrescribir archivos del sistema al extraer el contenido.

    La verificacion se aplica despues de normalizar la ruta con PurePosixPath,
    de manera que las secuencias ../ que se resuelven dentro del EPUB son aceptables
    (por ejemplo OEBPS/../images/cover.jpg que resuelve a images/cover.jpg) pero las
    que resultan en una ruta que comienza con .. o con / son rechazadas.
    """
    clean = str(PurePosixPath(zip_path))
    if clean.startswith("..") or clean.startswith("/"):
        raise ValueError(
            f"Ruta de archivo ZIP sospechosa: {zip_path!r}. "
            "El EPUB puede contener un ataque de tipo path traversal."
        )


def detect_prompt_injection(text: str, source: str = "fragmento") -> list[str]:
    """
    Busca en el texto patrones que sugieren un intento de manipular al modelo de
    lenguaje para que ignore sus instrucciones de sistema. No lanza excepcion: en
    su lugar devuelve la lista de patrones encontrados para que el llamador decida
    si rechazar el fragmento, traducirlo con una advertencia en el log, o reemplazarlo.

    Para la mayoria de los EPUBs legitimos esta funcion devuelve una lista vacia.
    Los falsos positivos son posibles en libros que hablan sobre seguridad informatica
    o sobre inteligencia artificial, por lo que bloquear el fragmento de forma
    automatica no es recomendable: es mejor registrar la advertencia y continuar.
    """
    found: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            found.append(pattern.pattern)
    if found:
        logger.warning(
            "Posible prompt injection detectado en %s: %d patron(es) encontrado(s). "
            "Se continua la traduccion con advertencia.",
            source,
            len(found),
        )
    return found
