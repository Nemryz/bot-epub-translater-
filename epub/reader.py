"""
Lector de archivos EPUB: abre el ZIP, parsea el OPF y devuelve la estructura del libro.

Su responsabilidad es abrir un archivo EPUB, leer su estructura interna, y devolver
una representacion en memoria que el resto del pipeline pueda usar sin necesidad de
conocer nada sobre el formato ZIP ni sobre el esquema XML del OPF. Toda la logica de
acceso al archivo esta encapsulada aqui, de forma que si en el futuro el formato cambia
o se agrega soporte para una variante del estandar, solo este modulo necesita actualizarse.
"""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET


# Los namespaces XML que aparecen en los archivos internos del EPUB son URIs largas y
# poco legibles. Registrarlos aqui bajo alias cortos permite que ElementTree los use
# en las busquedas con sintaxis como "container:rootfile" en lugar de escribir la URI
# completa cada vez, lo cual hace el codigo de busqueda mucho mas claro.
NAMESPACES = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


# Un Chapter representa un archivo HTML del libro que forma parte del flujo principal
# de lectura, es decir, los que el lector debe mostrar en orden segun el spine del OPF.
# Se guarda tanto el href declarado en el manifest (que puede ser relativo al directorio
# del OPF) como la zip_path, que es la ruta resuelta y normalizada que se usa para leer
# el contenido directamente desde el ZIP sin calculos adicionales en cada acceso.
@dataclass
class Chapter:
    id: str
    href: str
    zip_path: str
    title: str = ""
    word_count: int = 0


# EpubMeta contiene los campos de metadatos del libro extraidos del bloque dc: del OPF.
# El campo opf_dir guarda el directorio base dentro del ZIP donde se encuentra el OPF,
# porque todas las rutas en el manifest son relativas a ese directorio, no a la raiz
# del ZIP. Sin este dato seria imposible resolver correctamente los hrefs de los capitulos.
@dataclass
class EpubMeta:
    title: str = ""
    author: str = ""
    language: str = ""
    publisher: str = ""
    opf_dir: str = ""


# EpubBook es el objeto principal que representa un libro abierto y listo para procesar.
# Mantiene una referencia al ZipFile abierto para poder leer capitulos bajo demanda,
# en lugar de cargar todo el contenido en memoria de una vez, lo cual seria inviable
# con libros que tienen imagenes de alta resolucion embebidas. El atributo _zip se marca
# como campo privado (convencion de guion bajo) para indicar que no debe accederse
# directamente desde fuera del modulo, sino siempre a traves del metodo read_chapter.
@dataclass
class EpubBook:
    meta: EpubMeta = field(default_factory=EpubMeta)
    chapters: list[Chapter] = field(default_factory=list)
    epub_path: str = ""
    _zip: zipfile.ZipFile | None = field(default=None, repr=False)

    def close(self) -> None:
        # Cerrar el ZipFile explicitamente es importante porque Python no garantiza
        # el momento exacto en que el garbage collector liberara el descriptor de archivo.
        # En sistemas con muchos libros procesados en paralelo, dejar ZipFiles abiertos
        # puede agotar los descriptores de archivo disponibles del sistema operativo.
        if self._zip:
            self._zip.close()
            self._zip = None

    def read_chapter(self, chapter: Chapter) -> bytes:
        # Lanzar RuntimeError en lugar de retornar None obliga al codigo que llama a
        # manejar este caso de forma explicita, evitando errores silenciosos mas adelante
        # en el pipeline cuando se intente parsear bytes vacios como HTML.
        if not self._zip:
            raise RuntimeError(
                "El archivo EPUB no esta abierto. Llama a open_epub antes de leer capitulos."
            )
        return self._zip.read(chapter.zip_path)


# La funcion _find_opf_path implementa el primer paso obligatorio del protocolo de
# apertura de un EPUB: leer el archivo container.xml para descubrir donde esta el OPF.
# Esta indirection existe porque el estandar EPUB permite que el OPF este en cualquier
# subcarpeta del ZIP, no necesariamente en la raiz. Sin leer container.xml primero,
# no hay forma confiable de encontrar el OPF en todos los EPUBs validos.
def _find_opf_path(zf: zipfile.ZipFile) -> str:
    raw = zf.read("META-INF/container.xml")
    root = ET.fromstring(raw)

    # Se intenta primero la busqueda con el namespace registrado, que es la forma correcta
    # segun el estandar. Si falla (algunos EPUBs mal formados no declaran el namespace
    # correctamente en container.xml), se intenta con la URI completa como fallback.
    rootfile = root.find(".//container:rootfile", NAMESPACES)
    if rootfile is None:
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if rootfile is None:
        raise ValueError(
            "No se encontro el elemento rootfile en container.xml. "
            "El archivo puede estar corrupto o tener DRM."
        )

    path = rootfile.get("full-path")
    if not path:
        raise ValueError(
            "El atributo full-path del elemento rootfile esta vacio. El container.xml es invalido."
        )
    return path


# El directorio base del OPF es la parte del full-path que precede al nombre del archivo.
# Por ejemplo, si el OPF esta en OEBPS/content.opf, el directorio base es "OEBPS/".
# Este prefijo se antepone a todos los hrefs del manifest para obtener rutas absolutas
# dentro del ZIP. Si el OPF esta en la raiz del ZIP, el directorio base es una cadena vacia.
def _opf_base_dir(opf_path: str) -> str:
    parts = opf_path.rsplit("/", 1)
    return parts[0] + "/" if len(parts) == 2 else ""


# La resolucion de hrefs combina el directorio base del OPF con el href relativo del item
# del manifest y normaliza el resultado usando PurePosixPath para manejar correctamente
# los segmentos ../ que algunos EPUBs usan para referenciar archivos en carpetas hermanas.
# Por ejemplo, si el OPF esta en OEBPS/ y un href dice ../images/cover.jpg, la ruta
# resuelta debe ser images/cover.jpg, no OEBPS/../images/cover.jpg.
def _resolve_href(base_dir: str, href: str) -> str:
    combined = base_dir + href
    normalized = str(PurePosixPath(combined).resolve()).lstrip("/")
    return normalized


# La extraccion de metadatos intenta las dos formas de prefijo de namespace que aparecen
# en la practica: la forma con llaves {uri} que usa ElementTree internamente al parsear,
# y la busqueda sin prefijo que funciona cuando el OPF no declara el namespace
# explicitamente. Ninguno de los dos metodos cubre todos los casos por si solo.
def _parse_meta(root: ET.Element) -> EpubMeta:
    meta = EpubMeta()
    ns_dc = "{http://purl.org/dc/elements/1.1/}"
    ns_opf = "{http://www.idpf.org/2007/opf}"

    metadata = root.find(f"{ns_opf}metadata") or root.find("metadata")
    if metadata is None:
        return meta

    title_el = metadata.find(f"{ns_dc}title")
    if title_el is not None and title_el.text:
        meta.title = title_el.text.strip()

    creator_el = metadata.find(f"{ns_dc}creator")
    if creator_el is not None and creator_el.text:
        meta.author = creator_el.text.strip()

    language_el = metadata.find(f"{ns_dc}language")
    if language_el is not None and language_el.text:
        meta.language = language_el.text.strip()

    publisher_el = metadata.find(f"{ns_dc}publisher")
    if publisher_el is not None and publisher_el.text:
        meta.publisher = publisher_el.text.strip()

    return meta


# El manifest lista todos los recursos del libro: HTMLs, imagenes, CSS, fuentes, etc.
# Cada item tiene un id unico, un href relativo, y un media-type. Esta funcion construye
# un diccionario indexado por id porque el spine referencia los items por su id, no por
# su href, de manera que se necesita el diccionario para resolver la cadena spine -> id -> href.
def _parse_manifest(root: ET.Element, ns_opf: str) -> dict[str, dict]:
    manifest: dict[str, dict] = {}
    manifest_el = root.find(f"{ns_opf}manifest") or root.find("manifest")
    if manifest_el is None:
        return manifest
    for item in manifest_el:
        item_id = item.get("id", "")
        href = item.get("href", "")
        media_type = item.get("media-type", "")
        if item_id and href:
            manifest[item_id] = {"href": href, "media-type": media_type}
    return manifest


# El spine define el orden de lectura del libro como una lista de referencias a ids
# del manifest. Los items con atributo linear="no" son paginas auxiliares (paginas de
# portada alternativas, paginas de derechos de autor en formatos especiales, etc.) que
# los lectores pueden mostrar de forma opcional pero que no forman parte de la secuencia
# principal. Se excluyen para no traducir contenido que el usuario final probablemente
# nunca vera en el flujo normal de lectura.
def _parse_spine(root: ET.Element, ns_opf: str) -> list[str]:
    spine_el = root.find(f"{ns_opf}spine") or root.find("spine")
    if spine_el is None:
        return []
    idrefs = []
    for itemref in spine_el:
        linear = itemref.get("linear", "yes")
        if linear.lower() == "no":
            continue
        idref = itemref.get("idref", "")
        if idref:
            idrefs.append(idref)
    return idrefs


# La estimacion de palabras usa una expresion regular simple que cuenta secuencias de
# caracteres alfanumericos. No es un conteo preciso (ignora la puntuacion adherida,
# no distingue palabras reales de numeros o codigos), pero es suficientemente buena
# para mostrar al usuario una estimacion de costo y tiempo antes de confirmar la traduccion.
def _estimate_words(html_bytes: bytes) -> int:
    text = html_bytes.decode("utf-8", errors="replace")
    words = re.findall(r"\b\w+\b", text)
    return len(words)


# open_epub es la unica funcion publica de este modulo y el punto de entrada de todo
# el pipeline de traduccion. Recibe la ruta del archivo en disco y devuelve un EpubBook
# listo para usar. El ZipFile se mantiene abierto dentro del objeto devuelto, por lo que
# el llamador es responsable de invocar book.close() cuando termine de procesar el libro,
# o usar el objeto dentro de un bloque try/finally para garantizar el cierre incluso
# si ocurre un error durante la traduccion.
def open_epub(path: str) -> EpubBook:
    # La verificacion de ZIP antes de intentar abrirlo evita que el mensaje de error sea
    # el generico "bad magic number" de zipfile, reemplazandolo por uno que le dice al
    # usuario exactamente que el archivo no es un EPUB valido o que esta corrupto.
    if not zipfile.is_zipfile(path):
        raise ValueError(
            f"El archivo no es un ZIP valido y por lo tanto no puede ser un EPUB: {path}"
        )

    zf = zipfile.ZipFile(path, "r")
    names = set(zf.namelist())

    # La ausencia de META-INF/container.xml es el indicador mas confiable de que un archivo
    # tiene DRM, porque la proteccion digital cifra o reemplaza los archivos internos del
    # EPUB de forma que la estructura estandar no existe. Detectarlo aqui permite dar un
    # mensaje de error claro al usuario en lugar de fallar con una excepcion criptografica.
    if "META-INF/container.xml" not in names:
        zf.close()
        raise ValueError(
            "El archivo no contiene META-INF/container.xml. "
            "Probablemente tiene DRM (proteccion digital) o esta corrupto."
        )

    opf_path = _find_opf_path(zf)
    if opf_path not in names:
        zf.close()
        raise ValueError(f"El OPF declarado en container.xml no existe dentro del ZIP: {opf_path}")

    raw_opf = zf.read(opf_path)
    root = ET.fromstring(raw_opf)

    ns_opf = "{http://www.idpf.org/2007/opf}"
    base_dir = _opf_base_dir(opf_path)

    meta = _parse_meta(root)
    meta.opf_dir = base_dir

    manifest = _parse_manifest(root, ns_opf)
    spine_ids = _parse_spine(root, ns_opf)

    chapters: list[Chapter] = []
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if item is None:
            continue

        # Solo se incluyen los items cuyo media-type indica contenido HTML o XHTML.
        # El manifest puede incluir referencias a otros recursos como imagenes SVG o
        # documentos de navegacion que tambien son HTML pero no deben traducirse como
        # capitulos de texto, aunque el filtro por media-type es suficiente para la
        # mayoria de los casos.
        media_type = item.get("media-type", "")
        if "html" not in media_type and "xhtml" not in media_type:
            continue

        href = item["href"]
        zip_path = _resolve_href(base_dir, href)

        # Si la ruta resuelta no existe en el ZIP, se intenta con el href sin normalizar
        # y luego con el href solo. Esto cubre los casos donde la normalizacion de PurePosixPath
        # produce una ruta que no coincide exactamente con la que uso el editor del libro
        # al construir el ZIP, algo que ocurre con algunos editores de Windows que mezclan
        # barras diagonales y barras invertidas en los nombres de archivo.
        if zip_path not in names:
            alt = base_dir + href
            zip_path = alt if alt in names else href

        chapter = Chapter(id=item_id, href=href, zip_path=zip_path)
        try:
            raw = zf.read(zip_path)
            chapter.word_count = _estimate_words(raw)
        except KeyError:
            # Si el archivo del capitulo no existe en el ZIP, se incluye igualmente el
            # Chapter en la lista pero con word_count en cero, de forma que el resto del
            # pipeline pueda intentar procesarlo y reportar el error con mas contexto.
            pass
        chapters.append(chapter)

    return EpubBook(meta=meta, chapters=chapters, epub_path=path, _zip=zf)
