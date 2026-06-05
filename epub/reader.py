import zipfile
import os
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET


NAMESPACES = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


@dataclass
class Chapter:
    id: str
    href: str
    zip_path: str
    title: str = ""
    word_count: int = 0


@dataclass
class EpubMeta:
    title: str = ""
    author: str = ""
    language: str = ""
    publisher: str = ""
    opf_dir: str = ""


@dataclass
class EpubBook:
    meta: EpubMeta = field(default_factory=EpubMeta)
    chapters: list[Chapter] = field(default_factory=list)
    epub_path: str = ""
    _zip: zipfile.ZipFile | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._zip:
            self._zip.close()
            self._zip = None

    def read_chapter(self, chapter: Chapter) -> bytes:
        if not self._zip:
            raise RuntimeError("El archivo EPUB no esta abierto")
        return self._zip.read(chapter.zip_path)


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    raw = zf.read("META-INF/container.xml")
    root = ET.fromstring(raw)
    rootfile = root.find(
        ".//container:rootfile", NAMESPACES
    )
    if rootfile is None:
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if rootfile is None:
        raise ValueError("No se encontro el elemento rootfile en container.xml")
    path = rootfile.get("full-path")
    if not path:
        raise ValueError("El atributo full-path de rootfile esta vacio")
    return path


def _opf_base_dir(opf_path: str) -> str:
    parts = opf_path.rsplit("/", 1)
    return parts[0] + "/" if len(parts) == 2 else ""


def _resolve_href(base_dir: str, href: str) -> str:
    combined = base_dir + href
    normalized = str(PurePosixPath(combined).resolve()).lstrip("/")
    return normalized


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


def _estimate_words(html_bytes: bytes) -> int:
    text = html_bytes.decode("utf-8", errors="replace")
    import re
    words = re.findall(r"\b\w+\b", text)
    return len(words)


def open_epub(path: str) -> EpubBook:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"El archivo no es un ZIP valido: {path}")

    zf = zipfile.ZipFile(path, "r")
    names = set(zf.namelist())

    if "META-INF/container.xml" not in names:
        zf.close()
        raise ValueError("El archivo no tiene META-INF/container.xml; puede tener DRM o estar corrupto")

    opf_path = _find_opf_path(zf)
    if opf_path not in names:
        zf.close()
        raise ValueError(f"El OPF declarado en container.xml no existe en el ZIP: {opf_path}")

    raw_opf = zf.read(opf_path)
    root = ET.fromstring(raw_opf)

    ns_opf = "{http://www.idpf.org/2007/opf}"
    base_dir = _opf_base_dir(opf_path)

    meta = _parse_meta(root)
    meta.opf_dir = base_dir

    manifest = _parse_manifest(root, ns_opf)
    spine_ids = _parse_spine(root, ns_opf)

    chapters: list[Chapter] = []
    for position, item_id in enumerate(spine_ids):
        item = manifest.get(item_id)
        if item is None:
            continue
        media_type = item.get("media-type", "")
        if "html" not in media_type and "xhtml" not in media_type:
            continue
        href = item["href"]
        zip_path = _resolve_href(base_dir, href)
        if zip_path not in names:
            alt = base_dir + href
            zip_path = alt if alt in names else href
        chapter = Chapter(id=item_id, href=href, zip_path=zip_path)
        try:
            raw = zf.read(zip_path)
            chapter.word_count = _estimate_words(raw)
        except KeyError:
            pass
        chapters.append(chapter)

    book = EpubBook(meta=meta, chapters=chapters, epub_path=path, _zip=zf)
    return book
