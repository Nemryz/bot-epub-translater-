"""
Reempaquetador de EPUBs: produce el archivo de salida con los capitulos traducidos.

Se encarga del ultimo paso del pipeline: tomar el EPUB original y producir un nuevo
archivo donde los capitulos traducidos reemplazan a los originales, mientras que el
resto del contenido (imagenes, CSS, fuentes, OPF, tabla de contenidos) se copia sin
modificacion. De esta manera el libro de salida es estructuralmente identico al original
y funciona correctamente en cualquier lector de ebooks.
"""

import zipfile


# repack_epub es la unica funcion publica de este modulo. Recibe la ruta del EPUB
# original, un diccionario que mapea cada zip_path de capitulo a sus bytes HTML ya
# traducidos, y la ruta donde se debe escribir el archivo de salida. El diccionario
# translated_chapters se construye en la capa de traduccion usando los zip_path
# que el lector (epub/reader.py) proporciona, de manera que las claves coinciden
# exactamente con los nombres de archivo dentro del ZIP original.
def repack_epub(
    original_path: str,
    translated_chapters: dict[str, bytes],
    output_path: str,
) -> None:
    with zipfile.ZipFile(original_path, "r") as src:
        # ZIP_DEFLATED es el algoritmo de compresion estandar para EPUBs y produce
        # archivos de tamaño comparable al original. Usar ZIP_STORED (sin compresion)
        # produciria un archivo valido pero notablemente mas grande, lo cual es un
        # problema si el usuario necesita enviarlo a un lector con almacenamiento limitado.
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename in translated_chapters:
                    # Al escribir el capitulo traducido se reutiliza el objeto ZipInfo
                    # del archivo original, lo que preserva los metadatos del entry
                    # (fecha de modificacion, permisos) y garantiza que el nuevo EPUB
                    # es indistinguible del original en lo que respecta a la estructura
                    # del ZIP, algo que algunos lectores verifican al validar el archivo.
                    dst.writestr(item, translated_chapters[item.filename])
                else:
                    dst.writestr(item, src.read(item.filename))
