"""
Limpiador de HTML para preparar fragmentos de texto antes de enviarlos al motor de traduccion.

Su responsabilidad es recibir un elemento de BeautifulSoup que representa un bloque
de contenido del libro, recorrer su arbol de nodos hijo a hijo, y producir una
representacion de texto plano donde los tags HTML inline quedan reemplazados por tokens
numerados del formato [T01], [T02] para tags que envuelven texto traducible, y tokens
de posicion del formato [P01], [P02] para elementos que deben preservarse sin modificacion,
como imagenes, codigo fuente o elementos interactivos. El resultado es una cadena de texto
que el motor de traduccion puede procesar sin ver ni alterar las marcas de formato HTML
del original, porque esas marcas ya no estan en el texto sino registradas en el diccionario
token_map que este modulo devuelve junto con el texto limpio. El modulo gemelo
epub/html_restorer.py realiza el proceso inverso una vez que la traduccion esta disponible.
"""

import logging
from dataclasses import dataclass, field

from bs4 import Comment, NavigableString, Tag

logger = logging.getLogger(__name__)

# Los tags inline que envuelven texto traducible son aquellos cuya funcion semantica
# es modificar el estilo o el significado del texto que contienen, como el enfasis,
# las citas, las abreviaturas, los superindices o los hipervinculos, pero cuyo
# contenido forma parte del flujo de lectura normal y debe procesarse por el motor
# de traduccion junto con el texto que los rodea. A diferencia de los elementos
# no traducibles, estos tags pueden contener otros tags inline anidados, y el
# sistema de tokens maneja ese anidamiento correctamente porque cada nivel recibe
# su propio par de tokens de apertura y cierre con su numero correspondiente.
INLINE_TAGS: frozenset[str] = frozenset({
    "a", "abbr", "acronym", "b", "bdo", "big",
    "cite", "del", "dfn", "em", "i",
    "ins", "kbd", "label", "mark", "q", "s", "samp",
    "small", "span", "strong", "sub", "sup", "time",
    "tt", "u", "var",
})

# Los tags no traducibles agrupan dos categorias de elementos. La primera son los
# elementos visuales o autonomos que no contienen texto en lenguaje natural, como
# imagenes, saltos de linea, lineas horizontales o elementos de formulario. La segunda
# son los elementos cuyo contenido, aunque sea texto, no debe traducirse porque es
# codigo fuente, matematicas formales o contenido multimedia. Ambas categorias se
# tratan igual: se reemplazan en su totalidad por un token de posicion que preserva
# exactamente el elemento original incluyendo todos sus atributos y su contenido.
NON_TRANSLATABLE_TAGS: frozenset[str] = frozenset({
    "br", "hr", "img", "code", "pre", "math", "script",
    "style", "audio", "video", "svg", "input", "button",
    "select", "textarea", "iframe", "ruby", "rp", "rt",
})


@dataclass
class CleanResult:
    """
    Encapsula el resultado de la limpieza de un elemento HTML.

    El campo text contiene el texto con tokens listo para enviar al motor de
    traduccion. El campo token_map registra la correspondencia entre cada token
    y el fragmento HTML que reemplaza, de forma que el restaurador puede reconstruir
    el HTML completo a partir de la respuesta del modelo. El campo fragment_type
    clasifica el fragmento para que la capa de traduccion pueda seleccionar el
    system prompt mas apropiado segun la complejidad del contenido. Los campos
    wrap_open y wrap_close contienen la serializacion del elemento raiz que el
    restaurador usa para envolver el texto traducido y reconstruir el elemento
    completo con todos sus atributos originales.
    """

    text: str
    token_map: dict[str, str] = field(default_factory=dict)
    fragment_type: str = "plain"
    wrap_open: str = ""
    wrap_close: str = ""


def _serialize_opening(tag: Tag) -> str:
    """
    Produce la serializacion de la etiqueta de apertura de un Tag de BeautifulSoup
    incluyendo todos sus atributos con sus valores exactos. El atributo class se
    deserializa desde la lista interna de BeautifulSoup a una cadena separada por
    espacios, que es el formato que espera el HTML estandar. Lo mismo aplica al
    atributo rel de los hipervinculos, que tambien se representa como lista en
    BeautifulSoup cuando contiene multiples valores.
    """
    attrs: list[str] = []
    for key, value in tag.attrs.items():
        if isinstance(value, list):
            value = " ".join(value)
        attrs.append(f'{key}="{value}"')
    attr_str = (" " + " ".join(attrs)) if attrs else ""
    return f"<{tag.name}{attr_str}>"


def _is_non_translatable(tag: Tag) -> bool:
    """
    Comprueba si un tag debe tratarse como elemento no traducible aunque su nombre
    no aparezca en NON_TRANSLATABLE_TAGS, basandose en el atributo translate=no
    del estandar HTML5 y en la clase notranslate que usan Google Translate y otras
    herramientas de localizacion para marcar contenido que no debe procesarse.
    """
    if tag.get("translate") == "no":
        return True
    classes = tag.get("class", [])
    if isinstance(classes, str):
        classes = [classes]
    return "notranslate" in classes


def clean_html(element: Tag) -> CleanResult:
    """
    Limpia un elemento HTML reemplazando tags inline y elementos no traducibles
    por tokens numerados, y devuelve el texto con tokens junto con el mapa de
    restauracion y la clasificacion del fragmento.

    El recorrido es recursivo: cuando se encuentra un tag inline, se emite su
    token de apertura, se recorren sus hijos con la misma logica, y luego se emite
    su token de cierre, lo que preserva correctamente el anidamiento de tags en
    la cadena tokenizada resultante.
    """
    t_counter = 0
    p_counter = 0
    token_map: dict[str, str] = {}
    parts: list[str] = []
    has_complex = False

    def _walk(node) -> None:
        nonlocal t_counter, p_counter, has_complex

        if isinstance(node, Comment):
            # Los comentarios HTML no contienen texto traducible pero si estan
            # presentes en el original deben reaparecer en la misma posicion en
            # la salida, porque algunos EPUBs los usan como marcadores que el CSS
            # o el JavaScript del libro utilizan para referenciar secciones.
            p_counter += 1
            tok = f"[P{p_counter:02d}]"
            token_map[tok] = str(node)
            parts.append(tok)
            return

        if isinstance(node, NavigableString):
            parts.append(str(node))
            return

        if not isinstance(node, Tag):
            return

        if node.name in NON_TRANSLATABLE_TAGS or _is_non_translatable(node):
            p_counter += 1
            tok = f"[P{p_counter:02d}]"
            # str(node) serializa el elemento completo incluyendo su contenido,
            # lo que garantiza que los elementos con contenido como <code>x = 1</code>
            # se preservan igual que los elementos vacios como <br/>.
            token_map[tok] = str(node)
            parts.append(tok)
            return

        if node.name in INLINE_TAGS:
            t_counter += 1
            n = t_counter
            open_tok = f"[T{n:02d}]"
            close_tok = f"[/T{n:02d}]"
            token_map[open_tok] = _serialize_opening(node)
            token_map[close_tok] = f"</{node.name}>"
            parts.append(open_tok)
            for child in node.children:
                _walk(child)
            parts.append(close_tok)
            return

        # Un elemento que no es ni inline ni no-traducible es un elemento de bloque
        # anidado dentro del bloque que se esta procesando, como un div o una tabla
        # dentro de un parrafo. Se marca el fragmento como "complex" para que la
        # capa de traduccion pueda decidir si procesarlo de forma diferente, pero
        # el recorrido continua para extraer el texto que contiene.
        has_complex = True
        for child in node.children:
            _walk(child)

    # Se serializa la etiqueta de apertura del elemento raiz para que el restaurador
    # pueda envolver el texto traducido con exactamente el mismo tag, incluyendo
    # todos sus atributos de clase, id y cualquier atributo de datos personalizado.
    wrap_open = _serialize_opening(element)
    wrap_close = f"</{element.name}>"

    for child in element.children:
        _walk(child)

    text = "".join(parts)

    if has_complex:
        fragment_type = "complex"
    elif "[T" in text or "[P" in text:
        fragment_type = "with_tokens"
    else:
        fragment_type = "plain"

    return CleanResult(
        text=text,
        token_map=token_map,
        fragment_type=fragment_type,
        wrap_open=wrap_open,
        wrap_close=wrap_close,
    )


def should_skip(element: Tag) -> bool:
    """
    Determina si un elemento no tiene contenido de texto que valga la pena traducir.

    Se usa antes de llamar a clean_html para filtrar elementos vacios, elementos que
    contienen solo espacios en blanco, y elementos cuyos unicos hijos son imagenes u
    otros elementos no traducibles que no aportan texto al flujo de lectura. Esto evita
    llamadas innecesarias al motor de traduccion y reduce el costo de la operacion.
    """
    return not element.get_text(strip=True)


# ----------------------------------------------------------------------------
# Nota para implementaciones futuras: mejoras identificadas al analizar
# repositorios de referencia en el estado del arte de traduccion de ebooks.
#
# 1. Tokens con nombre semantico (referencia: enfoque de quantransce):
#    En lugar de tokens genericos [T01], usar tokens que describan el tipo
#    de tag, como [EM01] para <em>, [STRONG01] para <strong>, [A01] para <a>.
#    El modelo de lenguaje puede usar esa informacion semantica para decidir
#    donde colocar el enfasis o el hipervinculo en la lengua destino, en lugar
#    de simplemente copiarlo en la posicion original. La desventaja es que los
#    tokens son mas largos y consumen mas del contexto disponible.
#
# 2. Validacion de conteo de tokens antes de aceptar la traduccion (referencia:
#    enfoque de oomol-lab): antes de aceptar la respuesta del modelo, verificar
#    que el numero de tokens [T] en la respuesta coincida con el del original.
#    Si no coincide, reenviar el fragmento con un prompt que explique el error
#    y pida correccion. Este mecanismo captura la mayoria de los casos donde el
#    modelo omite o duplica un marcador de formato.
#
# 3. Hints en el system prompt sobre cada token (mejora identificada al analizar
#    el comportamiento de los modelos con fragmentos complejos): incluir en el
#    system prompt una tabla que mapee cada token al tipo de enfasis que representa
#    en el texto original, de forma que el modelo pueda decidir de forma mas
#    informada donde colocar cada marcador en la traduccion.
#
# 4. Glosario como filtro previo a la tokenizacion (referencia: enfoque de
#    Mubumbutu): antes de recorrer el arbol, identificar en el texto los terminos
#    del glosario del usuario y envolverlos en tags especiales que el limpiador
#    convierte en tokens [TERM01]. El system prompt instruye al modelo a no traducir
#    los tokens TERM, lo que garantiza que los nombres propios y terminos tecnicos
#    se preserven sin postprocesamiento.
#
# 5. Modo bilingue en la estructura del CleanResult (planificado para Fase 8):
#    Agregar en CleanResult una lista paralela de segmentos de texto con sus
#    posiciones en el HTML original, de forma que el restaurador pueda insertar
#    la traduccion inmediatamente despues de cada segmento original y producir
#    la salida bilingue a nivel de oracion en lugar de a nivel de parrafo completo.
# ----------------------------------------------------------------------------
