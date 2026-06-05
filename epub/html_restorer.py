"""
Restaurador de HTML: reconstruye el marcado original a partir del texto traducido y los tokens.

Su responsabilidad es el proceso inverso al del modulo epub/html_cleaner.py, es decir,
recibir el texto devuelto por el motor de traduccion, que contiene los mismos tokens
numerados que el limpiador inserto, y reemplazar cada token por el fragmento HTML que le
corresponde segun el mapa registrado durante la limpieza. El resultado es el elemento HTML
completo con el texto en la lengua destino y con todos los tags de formato, los hipervinculos
y los elementos no traducibles en exactamente la misma posicion relativa que tenian en el
original, de forma que el capitulo traducido es estructuralmente identico al original y se
visualiza correctamente en cualquier lector de ebooks. Este modulo trabaja siempre con un
CleanResult producido por html_cleaner.py y no debe usarse con datos de otra procedencia.
"""

import logging
import re

from epub.html_cleaner import CleanResult

logger = logging.getLogger(__name__)

# El patron de expresion regular que identifica tokens en el texto traducido cubre
# tanto los tokens de tags inline ([T01] y [/T01]) como los de elementos de posicion
# ([P01]). El uso de expresiones regulares en lugar de busqueda por cadena directa
# permite detectar en una sola pasada todos los tokens presentes en el texto, incluyendo
# aquellos que el modelo haya generado de forma incorrecta, como tokens con numeros
# fuera de rango o con el formato ligeramente alterado, para poder limpiarlos antes
# de devolver el resultado final.
_TOKEN_PATTERN = re.compile(r"\[/?[TP]\d+\]")


def restore_html(translated_text: str, result: CleanResult) -> str:
    """
    Reconstruye el elemento HTML completo a partir del texto traducido y el CleanResult.

    Verifica que todos los tokens del original esten presentes en la traduccion,
    registra advertencias para los que faltan, elimina cualquier token residual
    no reconocido que el modelo haya generado, y devuelve el HTML reconstruido
    envuelto en la etiqueta raiz original con todos sus atributos.
    """
    expected_tokens = set(result.token_map.keys())
    found_tokens = set(_TOKEN_PATTERN.findall(translated_text))

    missing = expected_tokens - found_tokens
    extra = found_tokens - expected_tokens

    for tok in sorted(missing):
        # El modelo omitio un token, lo que significa que el tag HTML que ese
        # token representaba no aparecera en el texto traducido. Dependiendo del
        # tipo de tag, esto puede ser un problema menor (un span de estilo perdido)
        # o un problema semantico (un hipervinculo omitido). El log de advertencia
        # permite identificar los casos frecuentes y mejorar el prompt en fases
        # posteriores del desarrollo.
        logger.warning(
            "Token omitido por el modelo de traduccion: %s (correspondia al tag '%s')",
            tok,
            result.token_map.get(tok, "desconocido"),
        )

    if extra:
        # Tokens que el modelo genero por su cuenta y que no existen en el mapa
        # de restauracion. Pueden ser tokens que el modelo alucino, tokens de un
        # fragmento anterior copiados por error, o variaciones del formato esperado
        # que el patron de expresion regular igualmente detecta. Se eliminan en
        # la pasada de limpieza final para que no aparezcan como texto literal.
        logger.warning(
            "Tokens no reconocidos en la respuesta del modelo: %s (se eliminan del resultado)",
            sorted(extra),
        )

    restored = translated_text
    for token, html in result.token_map.items():
        restored = restored.replace(token, html)

    # Eliminar cualquier token residual que no haya sido reemplazado porque no estaba
    # en el mapa. Este paso garantiza que el HTML de salida no contenga texto con
    # formato de token que el lector de ebooks mostraria literalmente al usuario.
    restored = _TOKEN_PATTERN.sub("", restored)

    return f"{result.wrap_open}{restored}{result.wrap_close}"


def count_token_mismatches(translated_text: str, result: CleanResult) -> int:
    """
    Cuenta la cantidad de tokens del original que no aparecen en la traduccion.

    Este conteo es util para la capa de traduccion, que puede usar este numero
    para decidir si vale la pena reintentar la traduccion del fragmento con un
    prompt mas explicito, o si la cantidad de tokens faltantes es lo suficientemente
    baja como para aceptar el resultado con las advertencias del log.
    """
    expected = set(result.token_map.keys())
    found = set(_TOKEN_PATTERN.findall(translated_text))
    return len(expected - found)


# ----------------------------------------------------------------------------
# Nota para implementaciones futuras: estrategias de recuperacion ante errores
# del modelo de traduccion identificadas al analizar repositorios de referencia.
#
# 1. Reintentos con prompt de correccion (referencia: estrategia de epub-translator):
#    Cuando el conteo de tokens faltantes supera un umbral configurable, por ejemplo
#    mas del 10% de los tokens del fragmento segun count_token_mismatches, reenviar
#    el fragmento al modelo con un prompt adicional que incluya el texto original,
#    el texto traducido y la lista de tokens faltantes, pidiendo explicitamente que
#    corrija la traduccion preservando todos los marcadores. Este mecanismo reduce
#    significativamente la tasa de tokens omitidos en fragmentos con muchos tags.
#
# 2. Fallback al elemento original (referencia: enfoque de oomol-lab):
#    Si despues del reintento el fragmento sigue teniendo tokens faltantes criticos,
#    como hipervinculos o notas al pie, insertar el HTML original sin modificar en
#    lugar de la traduccion defectuosa y marcar el fragmento como no traducido en el
#    log, para que el usuario pueda identificarlo y revisarlo manualmente.
#
# 3. Reconstruccion difusa por embeddings (investigacion futura):
#    Para tokens cuya posicion exacta en el texto traducido no es determinable porque
#    el modelo cambio la estructura de la oracion, intentar inferir la posicion correcta
#    buscando la frase semanticamente mas proxima al contexto del token en el original.
#    Este enfoque requiere embeddings de texto y es significativamente mas costoso,
#    pero podria usarse como ultimo recurso para fragmentos criticos donde la
#    recuperacion exacta falla.
#
# 4. Funcion restore_bilingual para el modo bilingue (planificado para Fase 8):
#    Agregar una variante de restore_html que en lugar de reemplazar el elemento
#    original produzca dos elementos: primero el elemento original intacto y luego
#    el elemento traducido reconstruido, ambos envueltos en un contenedor con clases
#    CSS que permitan estilarlos de forma diferente en el lector de ebooks. Esta
#    funcion recibira el CleanResult original y el texto traducido, y podra reutilizar
#    toda la logica de verificacion de tokens de restore_html.
#
# 5. Normalizacion de espacios en blanco post-restauracion (mejora identificada
#    al analizar la salida de distintos modelos): algunos modelos de lenguaje
#    modifican los espacios alrededor de los tokens al traducir, lo que puede
#    producir HTML con dobles espacios o espacios antes de signos de puntuacion.
#    Una pasada de normalizacion de espacios en blanco despues de la restauracion
#    de tokens mejoraria la calidad visual del texto sin afectar el marcado HTML.
# ----------------------------------------------------------------------------
