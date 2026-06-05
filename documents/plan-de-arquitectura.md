# Plan de construccion del bot de traduccion de EPUBs

## Contexto

Este plan describe la construccion integral, desde un directorio completamente vacio, de un bot de Telegram capaz de recibir archivos de libro electronico en distintos formatos, traducirlos a traves de proveedores de inteligencia artificial configurables, y devolver el resultado como un documento listo para leer en cualquier dispositivo. El analisis previo de los repositorios de referencia identifico los problemas conceptuales que cada proyecto resolvio de forma acertada, asi como los puntos donde cada implementacion tuvo limitaciones o simplificaciones que le impidieron escalar, de manera que la construccion que describe este plan no replica el codigo de ninguna fuente, sino que toma las ideas mas solidas de cada una, las combina en una arquitectura unificada, y las mejora en los aspectos donde cada proyecto original fue insuficiente.

El producto final es un sistema modular escrito enteramente en Python, compuesto por un parser de EPUB que respeta la estructura interna del formato, un sistema de limpieza de HTML con placeholders numerados que protege los tags inline durante la traduccion, una capa de proveedores intercambiables que abstrae las llamadas a distintas APIs de lenguaje, un bot de Telegram construido sobre aiogram que gestiona el flujo completo de interaccion con el usuario, y una integracion con Calibre que expande los formatos aceptados en la entrada y permite reescribir los metadatos del libro traducido. Todo esto se implementa de forma incremental, subiendo cada etapa al repositorio de GitHub a medida que se completa, de modo que el historial de cambios refleje el avance progresivo del sistema.

---

## Repositorios de referencia, Calibre y extraccion de conceptos para la construccion desde cero

Este documento consolida el analisis tecnico de todos los repositorios relevantes y de Calibre como herramienta complementaria, con el objetivo de servir como guia de arquitectura para construir un sistema de traduccion de EPUBs desde cero, cuyo producto final es un bot de Telegram. Nada de lo descrito aqui implica copiar codigo existente: se trata de identificar que problema resolvio cada proyecto, como lo resolvio, por que esa solucion es mejor que las alternativas, y como reimplementar ese concepto de forma mas limpia y unificada.

---

## 1. quantrancse/epub-translator: preservacion de estructura y sistema de diccionarios

Este repositorio es el mas simple de todos pero resolvio bien dos problemas fundamentales que los mas sofisticados a veces descuidan: la preservacion fiel de la estructura interna del EPUB y el soporte para diccionarios de sustitucion post-traduccion.

Un archivo EPUB no es mas que un ZIP renombrado. Dentro contiene una serie de archivos HTML que representan los capitulos, un archivo OPF (Open Packaging Format) que es el manifiesto del libro y define el orden de lectura, un archivo NCX o nav.xhtml que es la tabla de contenidos navegable, carpetas de imagenes, hojas de estilo CSS, y en algunos casos fuentes tipograficas embebidas. El error que cometen muchos traductores caseros es extraer solo el texto visible, traducirlo, y reinsertarlo de cualquier manera, lo que rompe el TOC, desordena los capitulos, elimina los IDs de ancla que permiten la navegacion interna, y a veces corrompe el CSS. quantrancse resuelve esto correctamente: recorre el OPF para conocer el orden exacto de los archivos, procesa cada HTML respetando su posicion en el manifiesto, y al reempaquetar preserva la jerarquia de carpetas original. Esto es lo que hay que reimplementar, no la logica de traduccion que usa Google Translate.

El sistema de diccionarios de este repo funciona con un archivo de texto plano donde cada linea tiene el formato texto_traducido:reemplazo_personalizado. Despues de que el motor de traduccion entrega su resultado, se aplica una pasada de sustitucion sobre el texto final usando ese mapa. Es primitivo pero funciona. Lo que hay que mejorar en la reimplementacion es que este diccionario se inyecte como contexto en el system prompt del LLM en lugar de aplicarse como postprocesamiento ciego. De esa manera el modelo no solo sustituye terminos sino que entiende el glosario como parte de las instrucciones de traduccion y puede usarlo de forma contextualmente coherente.

El concepto de multiprocesamiento que implementa este repo tambien es relevante: divide los archivos HTML del libro entre workers paralelos para acelerar la traduccion. En la reimplementacion esto se traduce a tareas asyncio concurrentes en aiogram, donde varios capitulos pueden estar enviandose a la API simultaneamente mientras se espera respuesta de los anteriores.

---

## 2. slyh/epub-translator: estrategia de conversion HTML a texto plano y prompts diferenciados

Este repositorio aporto una solucion arquitectonica importante que los repos mas simples ignoraron: antes de enviar cualquier contenido al LLM, el texto debe limpiarse de HTML. El razonamiento es directo: si se le manda al modelo un parrafo con tags mezclados, el modelo podria devolver el HTML modificado, olvidar cerrar un tag, cambiar atributos, o simplemente confundirse entre el contenido que debe traducir y la estructura que debe preservar.

La implementacion concreta implica un parser que analiza cada nodo del arbol HTML y clasifica el contenido en tres categorias. La primera son parrafos completamente limpios de tags, donde el texto se extrae directamente y se traduce sin ningun preprocesamiento adicional. La segunda son parrafos que mezclan texto con tags inline como em, i, strong, b, span, donde se extrae el texto visible pero se registra la posicion y tipo de cada tag para poder reinsertarlos despues. La tercera son bloques HTML complejos con estructura anidada donde la conversion a texto plano no es trivial y se usa un prompt diferente.

Slyh tambien introduce el concepto de tener prompts distintos segun la naturaleza del fragmento. Un parrafo limpio recibe un prompt simple de traduccion. Un parrafo con HTML mezclado recibe un prompt que menciona explicitamente que el texto contiene marcadores que no deben modificarse. Esta diferenciacion de prompts por tipo de fragmento es la base correcta, aunque la reimplementacion la mejora con el sistema de placeholders descrito mas adelante.

El otro concepto importante de slyh es el limite de acumulacion de caracteres antes de enviar al API. En lugar de enviar un capitulo completo en una sola peticion, acumula parrafos hasta llegar a un umbral configurable y los envia juntos. Esto tiene dos beneficios: reduce la latencia por el numero de peticiones y permite que el modelo tenga contexto de varios parrafos seguidos, lo que mejora la coherencia de la traduccion entre oraciones adyacentes.

---

## 3. oomol-lab/epub-translator: agrupacion por tokens, cache, concurrencia y modo bilingue

Este es el repositorio arquitectonicamente mas maduro. Sus contribuciones son multiples y cada una merece analisis individual.

El sistema de agrupacion por tokens es la evolucion correcta del limite de caracteres de slyh. En lugar de acumular texto hasta un numero arbitrario de caracteres, oomol-lab cuenta tokens estimados para cada fragmento y agrupa hasta alcanzar el umbral. Esto maximiza el uso de la ventana de contexto del modelo sin arriesgarse a truncamiento. En la reimplementacion con Gemini 2.5 Flash, que tiene un contexto de un millon de tokens, este umbral puede subirse significativamente, pero la logica de agrupacion sigue siendo valida y necesaria para controlar el costo por peticion.

La cache de traducciones guarda en disco los resultados de cada fragmento traducido, indexados por un hash del texto original. Si el proceso se interrumpe y se reinicia, los fragmentos ya traducidos no se reprocesan. Mas importante aun, si el mismo texto aparece en multiples lugares del libro, se traduce una sola vez y el resultado se reutiliza.

El parametro de concurrencia permite enviar multiples grupos de fragmentos a la API simultaneamente. La implementacion correcta usa asyncio.Semaphore para limitar el numero de peticiones concurrentes respetando los rate limits del proveedor.

El concepto de modos de salida (reemplazar, agregar texto, agregar bloque) es elegante: le da al usuario control sobre el formato del output. La reimplementacion expone esto como opcion en el bot de Telegram.

Los callbacks de progreso son fundamentales para el bot. Cada vez que se completa un grupo de fragmentos, se llama a una funcion que recibe un float entre 0.0 y 1.0. En el bot esto se conecta a la edicion del mensaje de estado que se actualiza periodicamente. Telegram tiene un rate limit de edicion de mensajes de aproximadamente una edicion por segundo por chat, asi que el callback no debe dispararse en cada fragmento sino cada cierto porcentaje de avance.

---

## 4. jb41/translate-book: granularidad por capitulos y reanudacion

La contribucion de jb41 es conceptualmente simple pero operativamente critica: el trabajo de traduccion se puede pausar y reanudar a nivel de capitulo. Implementa esto guardando un archivo de estado donde cada capitulo tiene uno de tres estados: pendiente, en progreso, o completado. Al iniciar una traduccion, primero carga el estado si existe, salta los capitulos completados, y continua desde donde quedo.

Esto es especialmente importante para el bot de Telegram por dos razones. La primera es que el servidor puede reiniciarse o la conexion puede cortarse, y no tiene sentido retraducir capitulos ya procesados cuando el usuario retoma el trabajo. La segunda es que en libros muy largos el usuario podria querer traducir primero los primeros capitulos para evaluar la calidad antes de comprometer el costo de tokens de todo el libro.

El concepto de mostrar los capitulos antes de traducir tambien permite al bot hacer una estimacion de costo real. Con los titulos y tamaños de cada capitulo, el bot puede calcular los tokens aproximados de todo el libro y decirle al usuario cuanto tardara y cuanto costara aproximadamente.

---

## 5. Mubumbutu/EPUB-SRT-LLM-Translator: sistema de placeholders para HTML inline

Este repositorio tiene la solucion mas robusta al problema de enviar HTML mezclado con texto al LLM. En lugar de extraer el texto y perder los tags, o enviar el HTML completo y esperar que el modelo lo preserve correctamente, Mubumbutu implementa un sistema de placeholders numerados.

El proceso funciona asi: antes de enviar un fragmento al modelo, se recorre el arbol de nodos del parrafo y se reemplazan los tags inline por tokens con formato [T01], [T02], [T03]. Se guarda un mapa que relaciona cada token con el tag original que reemplaza, incluyendo todos sus atributos. Los elementos que no deben traducirse en absoluto se marcan como tokens de posicion [P01], [P02]. El texto limpio resultante, que ahora contiene solo los tokens numerados en lugar de los tags reales, es lo que se envia al modelo. Despues de recibir la traduccion, se recorre el texto traducido y se restauran los tokens a sus tags originales usando el mapa guardado.

Este sistema tiene varias ventajas. El modelo no necesita saber nada sobre HTML y trabaja con texto que parece estructura de marcadores abstractos. Si el modelo olvida un token, la restauracion puede detectarlo y generar un warning en lugar de producir HTML silenciosamente malformado.

---

## 6. hydropix/TranslateBooksWithLLMs: arquitectura de providers intercambiables

Este repositorio es el unico que tiene soporte nativo para Gemini y DeepSeek como providers diferenciados. Su aporte conceptual es la abstraccion correcta de los backends de traduccion como providers intercambiables con una interfaz comun.

La implementacion concreta usa un patron de estrategia: existe una clase base abstracta TranslationProvider con metodos translate y estimate_tokens, y cada proveedor implementa esa interfaz de forma independiente. El codigo de procesamiento del EPUB no sabe ni le importa que proveedor esta usando. Agregar un nuevo proveedor en el futuro implica solo crear una nueva clase que implemente la interfaz, sin tocar nada mas del sistema.

---

## 7. KazKozDev/book-translator: traduccion en dos pasadas con auto-reflexion

Este repositorio introduce el concepto mas sofisticado del conjunto: en lugar de traducir en una sola pasada, usa dos llamadas al LLM por fragmento. La primera pasada produce la traduccion inicial. La segunda pasada le envia al mismo modelo tanto el texto original como la traduccion generada, y le pide que evalue si la traduccion es natural, precisa, y si preserva el tono y registro del original.

El costo es el doble de tokens por fragmento, lo que hace este modo inapropiado para uso casual con presupuesto limitado. Sin embargo, para textos donde la calidad es critica, la mejora es notable. En la reimplementacion esto se expone como una opcion premium que el usuario puede activar explicitamente, sabiendo que el proceso tomara el doble de tiempo y consumira el doble de tokens.

---

## 8. Calibre: conversion de formatos, metadatos y analisis previo

Calibre es software completamente libre y open source, distribuido bajo licencia GNU GPL v3. Esta escrito principalmente en Python y es la herramienta de gestion de ebooks mas usada en el mundo.

El primer aporte es la conversion de formatos. El ejecutable ebook-convert acepta EPUB, MOBI, AZW3, FB2, HTML, ODT, PDF, RTF, DOCX y varios mas en la entrada, y puede generar EPUB entre otros formatos en la salida. Esto significa que el bot no necesita rechazar archivos que no sean EPUB: puede recibirlos, convertirlos, y procesarlos.

El segundo aporte es la gestion de metadatos mediante ebook-meta. Al recibir un archivo, el bot puede extraer titulo, autor, idioma original y otros campos. Despues de la traduccion, puede escribir los metadatos actualizados: cambiar el idioma, agregar una indicacion de traduccion al titulo, y mantener el autor original.

El tercer aporte es la deteccion de EPUBs con DRM. Calibre puede detectar si un archivo tiene proteccion digital y notificar al usuario que no puede procesarse, en lugar de fallar silenciosamente con un error criptico.

La forma correcta de integrar Calibre es exclusivamente a traves de su CLI mediante subprocess, no de su API de plugins. La API de plugins esta disenada para extender la GUI de escritorio y requiere correr dentro del interprete Python embebido de Calibre. Usar subprocess para llamar a ebook-convert y ebook-meta desde el codigo Python del bot es mas limpio, mas portable, y mas facil de mantener.

---

## Sintesis tecnica: que tomar de cada fuente

De quantrancse se toman los conceptos de recorrido del OPF para determinar el orden de archivos, preservacion de la jerarquia de carpetas al reempaquetar, y el sistema de glosario como mapa de sustitucion mejorado a inyeccion en el system prompt. De slyh se toman los conceptos de conversion HTML a texto plano por tipo de fragmento, prompts diferenciados segun la naturaleza del contenido, y el sistema de acumulacion hasta umbral. De oomol-lab se toman los conceptos de agrupacion por tokens estimados, cache de traducciones en disco, concurrencia controlada con semaforo, modos de salida, y callbacks de progreso para el bot. De jb41 se toman los conceptos de estado de trabajo por capitulo, reanudacion desde punto de interrupcion, y listado previo de capitulos con estimacion de costo. De Mubumbutu se toma el sistema de placeholders numerados para tags HTML inline, con mapa de sustitucion y restauracion post-traduccion. De hydropix se toma la arquitectura de providers intercambiables con interfaz abstracta comun. De KazKozDev se toma el concepto de segunda pasada de revision como modo opcional de calidad. De Calibre se toma la conversion de formatos, la escritura de metadatos post-traduccion, el analisis previo del archivo, y la deteccion de DRM.

Todo lo anterior se implementa desde cero en Python, sin copiar ningun codigo de estos repositorios, usando sus soluciones como referencia conceptual y mejoran-dolas en los puntos donde cada uno tenia limitaciones.

---

## Parte 1: preparacion del entorno y creacion del repositorio

### Herramientas que deben estar instaladas antes de comenzar

Python 3.11 o superior, porque la libreria aiogram en su version 3 requiere soporte de anotaciones de tipo modernas y de asyncio con la API de alto nivel que se estabilizo en esa version. Git, para el control de versiones local y la sincronizacion con GitHub. La interfaz de linea de comandos de GitHub, conocida como gh CLI, que permite crear repositorios remotos directamente desde la terminal sin necesidad de usar el navegador. Calibre, que debe instalarse como aplicacion del sistema porque se usa exclusivamente a traves de sus ejecutables de consola, a saber ebook-convert y ebook-meta, y no a traves de su API de plugins.

### Flujo de trabajo con GitHub

A partir de la Fase 2, el flujo de trabajo recomendado es crear una rama separada para cada fase, desarrollar en esa rama, y hacer merge a main cuando la fase este completa y verificada. Esto permite revisar el historial de cambios por fase, revertir una fase entera si algo sale mal, y mantener la rama main siempre en un estado funcional:

    git checkout -b fase-N-nombre
    git add .
    git commit -m "fase N: descripcion"
    git push -u origin fase-N-nombre
    gh pr create --title "Fase N" --body "descripcion"
    gh pr merge --squash

El flag --squash comprime todos los commits de la rama en uno solo en main, lo que mantiene el historial limpio y legible. Cada entrada en el historial de main corresponde a una fase completa del proyecto.

---

## Parte 2: estructura de directorios del proyecto

    bot-epub-translater/
    ├── bot/
    │   ├── __init__.py
    │   ├── main.py              (punto de entrada, configura aiogram y registra routers)
    │   ├── handlers/
    │   │   ├── __init__.py
    │   │   ├── start.py         (comandos /start, /help, /cancel)
    │   │   ├── upload.py        (recepcion del archivo, FSM de sesion)
    │   │   ├── settings.py      (seleccion de idioma, proveedor, modo, calidad)
    │   │   └── progress.py      (actualizaciones de progreso al usuario)
    │   └── keyboards.py         (teclados inline reutilizables)
    ├── epub/
    │   ├── __init__.py
    │   ├── reader.py            (abre el ZIP, lee el OPF, determina el orden de capitulos)
    │   ├── html_cleaner.py      (convierte HTML a texto con placeholders numerados)
    │   ├── html_restorer.py     (restaura los placeholders al HTML original post-traduccion)
    │   └── packager.py          (reempaqueta el EPUB traducido preservando la jerarquia)
    ├── translation/
    │   ├── __init__.py
    │   ├── base.py              (clase abstracta TranslationProvider con interfaz comun)
    │   ├── gemini.py            (implementacion para Gemini 2.5 Flash)
    │   ├── deepseek.py          (implementacion para DeepSeek via openai-compatible SDK)
    │   └── grouper.py           (agrupa fragmentos por tokens estimados antes de enviar)
    ├── state/
    │   ├── __init__.py
    │   ├── job.py               (clase TranslationJob con estado por capitulo)
    │   └── cache.py             (cache de traducciones en disco indexada por hash SHA256)
    ├── calibre/
    │   ├── __init__.py
    │   ├── converter.py         (wrapper de subprocess para ebook-convert)
    │   └── metadata.py          (wrapper de subprocess para ebook-meta)
    ├── documents/
    │   └── plan-de-arquitectura.md
    ├── config.py
    ├── requirements.txt
    ├── .env.example
    └── README.md

---

## Parte 3: Fase 1, el esqueleto del proyecto

Esta es la primera fase que se sube al repositorio. El objetivo es tener un proyecto Python funcional, con las dependencias declaradas, la configuracion de variables de entorno lista, y el bot de Telegram respondiendo al comando /start, aunque todavia sin ninguna logica de traduccion.

### Dependencias

    aiogram==3.10.0
    google-generativeai==0.7.0
    openai==1.40.0
    beautifulsoup4==4.12.3
    lxml==5.2.2
    python-dotenv==1.0.1
    aiofiles==23.2.1
    httpx==0.27.0

aiogram es el framework asincrono para bots de Telegram, elegido sobre python-telegram-bot por su soporte nativo de asyncio y su sistema de filtros y routers que escala bien. google-generativeai es el SDK oficial de Google para acceder a Gemini. openai se usa para DeepSeek porque DeepSeek expone una API compatible con el protocolo de OpenAI, lo que significa que el mismo cliente puede usarse apuntando a un base_url diferente. beautifulsoup4 con el parser lxml es el conjunto estandar para manipular HTML en Python de forma robusta.

---

## Parte 4: Fase 2, el lector de EPUB

Esta fase implementa el modulo epub/reader.py, que es el corazon del parser. Un archivo EPUB es un ZIP renombrado con extension .epub. Dentro de ese ZIP existe siempre un archivo llamado mimetype en la raiz, una carpeta META-INF que contiene container.xml, el cual apunta a la ubicacion del archivo OPF. El OPF contiene tres secciones fundamentales: metadata con el titulo y autor, manifest que lista todos los archivos del libro, y spine que define el orden de lectura.

El lector hace estas operaciones en orden: abrir el archivo como ZIP, leer container.xml y extraer la ruta al OPF, parsear el manifest para construir un diccionario de items, leer el spine y extraer la lista de idrefs en orden, y para cada archivo HTML calcular su ruta absoluta dentro del ZIP. Los casos borde que se manejan incluyen rutas con ../ en los hrefs del manifest, el atributo xml:lang en los metadatos, y los items del spine con atributo linear="no" que son paginas auxiliares y no deben incluirse en el flujo principal.

---

## Parte 5: Fase 3, la limpieza de HTML y el sistema de placeholders

Esta es la fase mas delicada del proyecto porque define como se comunica el parser de HTML con el motor de traduccion. El modulo html_cleaner.py recibe un objeto BeautifulSoup que representa un parrafo, recorre el arbol de nodos, reemplaza los tags inline por tokens con formato [T01], [T02], guarda un mapa de cada token al tag original con todos sus atributos, reemplaza los elementos no traducibles por tokens [P01], [P02], y devuelve el texto limpio con tokens. El modulo html_restorer.py hace el proceso inverso: recorre la cadena traducida, encuentra cada token, y lo reemplaza por el tag HTML original del mapa. Si el modelo omitio un token, el restorer genera una advertencia en el log pero continua.

---

## Parte 6: Fase 4, los proveedores de traduccion

La clase base abstracta en translation/base.py define la interfaz con tres elementos: el metodo asincrono translate que recibe texto y system prompt y devuelve texto traducido, el metodo estimate_tokens que usa la aproximacion de un token por cada cuatro caracteres, y la propiedad name que identifica el proveedor. gemini.py implementa esta interfaz usando generate_content_async del SDK de Google con temperatura 0.3. deepseek.py implementa la misma interfaz usando el cliente openai apuntando a api.deepseek.com/v1 con el modelo deepseek-chat. grouper.py acumula fragmentos hasta alcanzar 4000 tokens por grupo antes de enviarlos al proveedor.

---

## Parte 7: Fase 5, el bot de Telegram

El handler upload.py descarga el archivo al directorio downloads/ con nombre unico generado con uuid4, extrae la extension, y si no es EPUB llama al conversor de Calibre antes de continuar. El handler settings.py guia al usuario por cuatro pantallas sucesivas: idioma, proveedor, modo de salida, y nivel de calidad. El handler progress.py implementa el mecanismo de actualizacion del mensaje de estado respetando el rate limit de Telegram de una edicion por segundo por chat.

---

## Parte 8: Fase 6, la cache y la reanudacion

El modulo state/cache.py nombra cada entrada de cache con el hash SHA256 del texto original calculado con hashlib. Antes de enviar cualquier fragmento al proveedor, el sistema busca en la cache. Si existe, usa el resultado del disco sin hacer ninguna llamada a la API. Si no existe, llama, guarda, y continua. El modulo state/job.py mantiene el estado del proceso a nivel de capitulo con tres estados posibles: pending, in_progress, y completed. Al reanudar, carga el archivo de estado y salta los capitulos ya completados.

---

## Parte 9: Fase 7, la integracion con Calibre

calibre/converter.py usa asyncio.create_subprocess_exec para no bloquear el event loop del bot mientras Calibre hace la conversion. calibre/metadata.py implementa read_metadata para extraer campos del libro y write_metadata para actualizar el idioma, el titulo, y los demas campos del EPUB de salida. La deteccion de DRM se hace inspeccionando el contenido del ZIP antes de procesarlo: si los archivos internos son ilegibles o tienen estructura distinta a la de un EPUB normal, el sistema informa al usuario en lugar de fallar con un error tecnico.

---

## Parte 10: Fase 8, las funcionalidades avanzadas

El modo bilingue expone tres opciones al usuario en el teclado de configuracion: reemplazar, bilingue inline, y bilingue bloque. El modo de calidad aplica una segunda llamada al LLM que evalua unicamente tres aspectos: nombres propios incorrectamente traducidos, terminos del glosario no respetados, y frases poco naturales en el idioma de destino. Si no detecta problemas, devuelve la traduccion sin cambios con costo adicional minimo. El glosario se inyecta directamente en el system prompt de cada llamada, lo que permite al modelo usarlo de forma contextualmente coherente en lugar de aplicar una sustitucion ciega posterior.

---

## Verificacion end-to-end

Iniciar el bot con python -m bot.main y verificar que no haya errores en la terminal. Enviar /start al bot en Telegram y verificar el mensaje de bienvenida. Subir un EPUB corto de dominio publico del Proyecto Gutenberg y seguir el flujo completo. Verificar que el mensaje de progreso se actualice durante la traduccion. Descargar el EPUB de salida, abrirlo en Calibre o Foliate, y verificar que el texto este en el idioma de destino, que la tabla de contenidos funcione, y que las imagenes y el formato se hayan preservado. Interrumpir el proceso a la mitad, reiniciar el bot, subir el mismo archivo, y verificar que el sistema retome desde el capitulo donde se detuvo sin retraducir los anteriores.
