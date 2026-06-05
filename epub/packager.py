import zipfile
import os
import shutil
from pathlib import Path


def repack_epub(
    original_path: str,
    translated_chapters: dict[str, bytes],
    output_path: str,
) -> None:
    """
    Crea un nuevo EPUB copiando todos los archivos del original
    y reemplazando los capitulos con las versiones traducidas.
    translated_chapters: mapa de zip_path -> bytes del HTML traducido.
    """
    with zipfile.ZipFile(original_path, "r") as src:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename in translated_chapters:
                    dst.writestr(item, translated_chapters[item.filename])
                else:
                    dst.writestr(item, src.read(item.filename))
