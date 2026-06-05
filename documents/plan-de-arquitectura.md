# Plan de construccion del bot de traduccion de EPUBs

## Contexto

Este plan describe la construccion integral, desde un directorio completamente vacio, de un bot de Telegram capaz de recibir archivos de libro electronico en distintos formatos, traducirlos a traves de proveedores de inteligencia artificial configurables, y devolver el resultado como un documento listo para leer en cualquier dispositivo. El analisis previo de los repositorios de referencia identifico los problemas conceptuales que cada proyecto resolvio de forma acertada, asi como los puntos donde cada implementacion tuvo limitaciones o simplificaciones que le impidieron escalar, de manera que la construccion que describe este plan no replica el codigo de ninguna fuente, sino que toma las ideas mas solidas de cada una, las combina en una arquitectura unificada, y las mejora en los aspectos donde cada proyecto original fue insuficiente.

El producto final es un sistema modular escrito enteramente en Python, compuesto por un parser de EPUB que respeta la estructura interna del formato, un sistema de limpieza de HTML con placeholders numerados que protege los tags inline durante la traduccion, una capa de proveedores intercambiables que abstrae las llamadas a distintas APIs de lenguaje, un bot de Telegram construido sobre aiogram que gestiona el flujo completo de interaccion con el usuario, y una integracion con Calibre que expande los formatos aceptados en la entrada y permite reescribir los metadatos del libro traducido. Todo esto se implementa de forma incremental, subiendo cada etapa al repositorio de GitHub a medida que se completa, de modo que el historial de cambios refleje el avance progresivo del sistema.

Un segundo ciclo de analisis, realizado despues de la implementacion de las tres primeras fases, identifico una coleccion mas amplia de proyectos open source que abordan el mismo problema desde angulos distintos: bots de Telegram que manejan preferencias por usuario, sistemas de traduccion batch con control de rate limiting por proveedor, pipelines de exportacion a multiples formatos, herramientas con interfaces graficas de revision de calidad, y traductores de comics con OCR. Este segundo analisis no cambia la arquitectura fundamental ya implementada, sino que enriquece el catalogo de mejoras posibles para cada fase y abre la puerta a funcionalidades adicionales que pueden implementarse despues de la Fase 8 sin necesidad de refactorizar el nucleo del sistema.

---

## Repositorios de referencia originales: analisis y extraccion de conceptos

Este documento consolida el analisis tecnico de todos los repositorios relevantes y de Calibre como herramienta complementaria, con el objetivo de servir como guia de arquitectura para construir un sistema de traduccion de EPUBs desde cero, cuyo producto final es un bot de Telegram. Nada de lo descrito aqui implica copiar codigo existente: se trata de identificar que problema resolvio cada proyecto, como lo resolvio, por que esa solucion es mejor que las alternativas, y como reimplementar ese concepto de forma mas limpia y unificada.

---

## 1. quantrancse/epub-translator: preservacion de estructura y sistema de diccionarios

Este repositorio es el mas simple de todos pero resolvio bien dos problemas fundamentales que los mas sofisticados a veces descuidan: la preservacion fiel de la estructura interna del EPUB y el soporte para diccionarios de sustitucion post-traduccion.

Un archivo EPUB no es mas que un ZIP renombrado. Dentro contiene una serie de archivos HTML que representan los capitulos, un archivo OPF que es el manifiesto del libro y define el orden de lectura, un archivo NCX o nav.xhtml que es la tabla de contenidos navegable, carpetas de imagenes, hojas de estilo CSS, y en algunos casos fuentes tipograficas embebidas. El error que cometen muchos traductores caseros es extraer solo el texto visible, traducirlo, y reinsertarlo de cualquier manera, lo que rompe el TOC, desordena los capitulos, elimina los IDs de ancla que permiten la navegacion interna, y a veces corrompe el CSS. quantrancse resuelve esto correctamente: recorre el OPF para conocer el orden exacto de los archivos, procesa cada HTML respetando su posicion en el manifiesto, y al reempaquetar preserva la jerarquia de carpetas original. Esto es lo que hay que reimplementar, no la logica de traduccion que usa Google Translate.

El sistema de diccionarios de este repo funciona con un archivo de texto plano donde cada linea tiene el formato texto_traducido:reemplazo_personalizado. Despues de que el motor de traduccion entrega su resultado, se aplica una pasada de sustitucion sobre el texto final usando ese mapa. Es primitivo pero funciona. Lo que hay que mejorar en la reimplementacion es que este diccionario se inyecte como contexto en el system prompt del LLM en lugar de aplicarse como postprocesamiento ciego. De esa manera el modelo no solo sustituye terminos sino que entiende el glosario como parte de las instrucciones de traduccion y puede usarlo de forma contextualmente coherente, respetando morfologia variable, plurales, y construcciones gramaticales que el postprocesamiento ciego no puede manejar correctamente.

El concepto de multiprocesamiento que implementa este repo tambien es relevante: divide los archivos HTML del libro entre workers paralelos para acelerar la traduccion. En la reimplementacion esto se traduce a tareas asyncio concurrentes en aiogram, donde varios capitulos pueden estar enviandose a la API simultaneamente mientras se espera respuesta de los anteriores, y el numero de peticiones concurrentes se controla con un asyncio.Semaphore para no superar el rate limit del proveedor.

Limitaciones de este repo que la reimplementacion supera: no tiene sistema de cache, no tiene reanudacion ante interrupciones, no soporta mas de un proveedor de traduccion, y su integracion con el usuario es minima porque opera desde la linea de comandos sin ninguna interfaz conversacional.

---

## 2. slyh/epub-translator: estrategia de conversion HTML a texto plano y prompts diferenciados

Este repositorio aporto una solucion arquitectonica importante que los repos mas simples ignoraron: antes de enviar cualquier contenido al LLM, el texto debe limpiarse de HTML. El razonamiento es directo: si se le manda al modelo un parrafo con tags mezclados, el modelo podria devolver el HTML modificado, olvidar cerrar un tag, cambiar atributos, o simplemente confundirse entre el contenido que debe traducir y la estructura que debe preservar.

La implementacion concreta implica un parser que analiza cada nodo del arbol HTML y clasifica el contenido en tres categorias. La primera son parrafos completamente limpios de tags, donde el texto se extrae directamente y se traduce sin ningun preprocesamiento adicional. La segunda son parrafos que mezclan texto con tags inline como em, i, strong, b, span, donde se extrae el texto visible pero se registra la posicion y tipo de cada tag para poder reinsertarlos despues. La tercera son bloques HTML complejos con estructura anidada donde la conversion a texto plano no es trivial y se usa un prompt diferente que alerta al modelo de la presencia de marcadores especiales.

Slyh tambien introduce el concepto de tener prompts distintos segun la naturaleza del fragmento. Un parrafo limpio recibe un prompt simple de traduccion. Un parrafo con HTML mezclado recibe un prompt que menciona explicitamente que el texto contiene marcadores que no deben modificarse. Esta diferenciacion de prompts por tipo de fragmento es la base correcta, aunque la reimplementacion la mejora con el sistema de placeholders numerados descrito mas adelante, que hace innecesario mencionar tags HTML en el prompt y simplifica las instrucciones al modelo a solo preservar los tokens sin modificarlos.

El otro concepto importante de slyh es el limite de acumulacion de caracteres antes de enviar al API. En lugar de enviar un capitulo completo en una sola peticion, acumula parrafos hasta llegar a un umbral configurable y los envia juntos. Esto tiene dos beneficios: reduce la latencia por el numero de peticiones y permite que el modelo tenga contexto de varios parrafos seguidos, lo que mejora la coherencia de la traduccion entre oraciones adyacentes de distintos parrafos.

---

## 3. oomol-lab/epub-translator: agrupacion por tokens, cache, concurrencia y modo bilingue

Este es el repositorio arquitectonicamente mas maduro de los analizados en el primer ciclo. Sus contribuciones son multiples y cada una merece analisis individual porque cada una resuelve un problema real que se manifiesta cuando se escala la traduccion a libros de longitud real.

El sistema de agrupacion por tokens es la evolucion correcta del limite de caracteres de slyh. En lugar de acumular texto hasta un numero arbitrario de caracteres, oomol-lab cuenta tokens estimados para cada fragmento y agrupa hasta alcanzar el umbral. Esto maximiza el uso de la ventana de contexto del modelo sin arriesgarse a truncamiento. En la reimplementacion con Gemini 2.5 Flash, que tiene un contexto de un millon de tokens, este umbral puede subirse significativamente, pero la logica de agrupacion sigue siendo valida y necesaria para controlar el costo por peticion y mantener coherencia en la respuesta del modelo.

La cache de traducciones guarda en disco los resultados de cada fragmento traducido, indexados por un hash del texto original. Si el proceso se interrumpe y se reinicia, los fragmentos ya traducidos no se reprocesan. Mas importante aun, si el mismo texto aparece en multiples lugares del libro, como un encabezado que se repite en el encabezado de cada pagina o un texto legal que aparece al inicio de cada capitulo, se traduce una sola vez y el resultado se reutiliza en todas las ocurrencias.

El parametro de concurrencia permite enviar multiples grupos de fragmentos a la API simultaneamente. La implementacion correcta usa asyncio.Semaphore para limitar el numero de peticiones concurrentes respetando los rate limits del proveedor, de manera que si el limite es tres peticiones concurrentes, el cuarto grupo espera hasta que uno de los tres primeros termine antes de enviarse.

El concepto de modos de salida es elegante y le da al usuario control real sobre el formato del output sin necesidad de conocer nada sobre HTML. La reimplementacion expone esto como opcion en el teclado de configuracion del bot de Telegram con tres valores: reemplazar, bilingue inline, y bilingue bloque.

Los callbacks de progreso son fundamentales para el bot. Cada vez que se completa un grupo de fragmentos, se llama a una funcion que recibe un float entre 0.0 y 1.0. En el bot esto se conecta a la edicion del mensaje de estado que se actualiza periodicamente. Telegram tiene un rate limit de edicion de mensajes de aproximadamente una edicion por segundo por chat, asi que el callback no debe dispararse en cada fragmento sino cada cierto porcentaje de avance o cada cierto numero de segundos transcurridos.

---

## 4. jb41/translate-book: granularidad por capitulos y reanudacion

La contribucion de jb41 es conceptualmente simple pero operativamente critica: el trabajo de traduccion se puede pausar y reanudar a nivel de capitulo. Implementa esto guardando un archivo de estado donde cada capitulo tiene uno de tres estados: pendiente, en progreso, o completado. Al iniciar una traduccion, primero carga el estado si existe, salta los capitulos completados, y continua desde donde quedo.

Esto es especialmente importante para el bot de Telegram por dos razones. La primera es que el servidor puede reiniciarse o la conexion puede cortarse, y no tiene sentido retraducir capitulos ya procesados cuando el usuario retoma el trabajo. La segunda es que en libros muy largos el usuario podria querer traducir primero los primeros capitulos para evaluar la calidad antes de comprometer el costo de tokens de todo el libro.

El concepto de mostrar los capitulos antes de traducir tambien permite al bot hacer una estimacion de costo real. Con los titulos y tamaños de cada capitulo, el bot puede calcular los tokens aproximados de todo el libro y decirle al usuario cuanto tardara y cuanto costara aproximadamente, de manera que el usuario puede decidir si quiere traducir todo el libro o solo una seleccion de capitulos, y en el segundo caso puede indicar el rango exacto que le interesa.

---

## 5. Mubumbutu/EPUB-SRT-LLM-Translator: sistema de placeholders para HTML inline

Este repositorio tiene la solucion mas robusta al problema de enviar HTML mezclado con texto al LLM. En lugar de extraer el texto y perder los tags, o enviar el HTML completo y esperar que el modelo lo preserve correctamente, Mubumbutu implementa un sistema de placeholders numerados que protege el marcado sin ocultarlo completamente.

El proceso funciona de la siguiente manera: antes de enviar un fragmento al modelo, se recorre el arbol de nodos del parrafo y se reemplazan los tags inline por tokens con formato [T01], [T02], [T03]. Se guarda un mapa que relaciona cada token con el tag original que reemplaza, incluyendo todos sus atributos exactamente como estaban. Los elementos que no deben traducirse en absoluto, como imagenes, codigo fuente o elementos interactivos, se marcan como tokens de posicion [P01], [P02]. El texto limpio resultante, que ahora contiene solo los tokens numerados en lugar de los tags reales, es lo que se envia al modelo. Despues de recibir la traduccion, se recorre el texto traducido y se restauran los tokens a sus tags originales usando el mapa guardado.

Este sistema tiene varias ventajas sobre las alternativas. El modelo no necesita saber nada sobre HTML y trabaja con texto que parece marcadores abstractos, lo que le permite concentrarse en la tarea de traduccion sin distracciones. Si el modelo olvida un token, la restauracion puede detectarlo y generar un warning en lugar de producir HTML silenciosamente malformado. Si el modelo invierte el orden de dos tokens, el HTML resultante puede tener tags en orden distinto al original pero sigue siendo valido, lo que es un comportamiento aceptable cuando el modelo decide que la estructura de la oracion en la lengua destino requiere un orden diferente.

La mejora que aplica la reimplementacion sobre el sistema de Mubumbutu es agregar la funcion count_token_mismatches que permite a la capa de traduccion tomar decisiones sobre si reintentar la traduccion de un fragmento especifico basandose en el porcentaje de tokens omitidos, en lugar de simplemente registrar las advertencias y continuar con cualquier resultado que el modelo devuelva.

---

## 6. hydropix/TranslateBooksWithLLMs: arquitectura de providers intercambiables

Este repositorio es el unico del primer analisis que tiene soporte nativo para Gemini y DeepSeek como providers diferenciados. Su aporte conceptual es la abstraccion correcta de los backends de traduccion como providers intercambiables con una interfaz comun, de manera que el codigo de procesamiento del EPUB no necesita saber ni le importa que proveedor esta usando en un momento dado.

La implementacion concreta usa un patron de estrategia: existe una clase base abstracta TranslationProvider con metodos translate y estimate_tokens, y cada proveedor implementa esa interfaz de forma independiente. Agregar un nuevo proveedor en el futuro implica solo crear una nueva clase que implemente la interfaz, sin tocar nada mas del sistema. Esto es especialmente relevante porque el ecosistema de proveedores de LLM esta cambiando rapidamente: lo que hoy es el proveedor mas economico puede no serlo en seis meses, y el sistema debe poder incorporar nuevas opciones sin refactorizacion.

---

## 7. KazKozDev/book-translator: traduccion en dos pasadas con auto-reflexion

Este repositorio introduce el concepto mas sofisticado del primer conjunto de referencia: en lugar de traducir en una sola pasada, usa dos llamadas al LLM por fragmento. La primera pasada produce la traduccion inicial. La segunda pasada le envia al mismo modelo tanto el texto original como la traduccion generada, y le pide que evalue si la traduccion es natural, precisa, y si preserva el tono y registro del original.

El costo es el doble de tokens por fragmento, lo que hace este modo inapropiado para uso casual con presupuesto limitado. Sin embargo, para textos donde la calidad es critica, la mejora es notable especialmente en el manejo de modismos, metaforas, y construcciones idiomaticas que el modelo traduce de forma demasiado literal en la primera pasada. En la reimplementacion esto se expone como una opcion premium que el usuario puede activar explicitamente, sabiendo que el proceso tomara el doble de tiempo y consumira el doble de tokens.

La evaluacion de la segunda pasada es eficiente porque el modelo solo revisa tres aspectos concretos: nombres propios incorrectamente traducidos, terminos del glosario no respetados, y frases que suenan mecanicas o poco naturales en el idioma de destino. Si no detecta ningun problema en ninguno de los tres aspectos, devuelve la traduccion original sin modificacion, con lo cual el costo adicional en ese fragmento es solo el de los tokens del prompt de evaluacion, que es mucho menor que el de la traduccion completa.

---

## 8. Calibre: conversion de formatos, metadatos y analisis previo

Calibre es software completamente libre y open source, distribuido bajo licencia GNU GPL v3, escrito principalmente en Python, y es la herramienta de gestion de ebooks mas usada en el mundo con mas de dos decadas de desarrollo activo. La decision de integrarlo en este sistema no es solo de comodidad sino de cobertura: Calibre puede leer formatos que no tienen implementacion open source alternativa robusta, como AZW3 y los formatos propietarios de algunos fabricantes de lectores de ebooks.

El primer aporte de Calibre es la conversion de formatos. El ejecutable ebook-convert acepta EPUB, MOBI, AZW3, FB2, HTML, ODT, PDF, RTF, DOCX y varios mas en la entrada, y puede generar EPUB entre otros formatos en la salida. Esto significa que el bot no necesita rechazar archivos que no sean EPUB: puede recibirlos, convertirlos internamente, y procesarlos como si hubieran llegado en formato EPUB desde el principio.

El segundo aporte es la gestion de metadatos mediante ebook-meta. Al recibir un archivo, el bot puede extraer titulo, autor, idioma original y otros campos. Despues de la traduccion, puede escribir los metadatos actualizados: cambiar el idioma al codigo BCP 47 del idioma de destino, agregar una indicacion de traduccion al titulo como sufijo entre parentesis, y mantener el autor original sin modificacion.

El tercer aporte es la deteccion de EPUBs con DRM. Calibre puede detectar si un archivo tiene proteccion digital y notificar al usuario que no puede procesarse, en lugar de fallar silenciosamente con un error criptico que el usuario no sabria como interpretar.

La forma correcta de integrar Calibre es exclusivamente a traves de su CLI mediante subprocess, no de su API de plugins. La API de plugins esta disenada para extender la GUI de escritorio y requiere correr dentro del interprete Python embebido de Calibre, lo que crea un acoplamiento profundo con la version instalada y hace el codigo muy dificil de mantener. Usar subprocess para llamar a ebook-convert y ebook-meta desde el codigo Python del bot es mas limpio, mas portable, mas facil de testear, y no depende de la version interna de Calibre.

---

## Repositorios adicionales identificados en el analisis ampliado

El segundo ciclo de analisis, realizado despues de completar las fases 1, 2 y 3, identifico una coleccion mas amplia de proyectos que abordan el mismo espacio de problema desde angulos distintos y que aportan ideas concretas para mejorar las fases ya implementadas y para disenar funcionalidades futuras mas alla de la Fase 8.

---

## 9. jesselau76/ebook-GPT-translator: pipeline de extraccion y reinyeccion

Este repositorio implementa un pipeline limpio donde la traduccion opera sobre archivos de texto extraidos del EPUB, no sobre el HTML directamente. El proceso en dos pasos, primero extraer todo el texto del EPUB a un archivo intermedio y luego traducir ese archivo y reinyectarlo, tiene la ventaja de que el motor de traduccion nunca toca el HTML y no puede corromperlo accidentalmente. La desventaja es que pierde el contexto de marcado inline al extraer, lo que dificulta preservar negritas, cursivas y otros formatos en el texto de salida.

Lo que es util de este repo para la reimplementacion es su manejo del encoding de caracteres: detecta y normaliza codificaciones de texto antes de procesar cualquier archivo, lo que evita los errores de UnicodeDecodeError que son comunes en EPUBs con caracteres especiales o con encodings no estandar declarados incorrectamente en el XML del OPF. Esta logica de normalizacion de encoding deberia incorporarse al reader.py de la Fase 2 como una capa defensiva antes de cualquier decodificacion.

---

## 10. al-nemirov/epub-translator: modo batch y preservacion de estructura XML

La contribucion principal de este repositorio es el modo batch: en lugar de procesar un solo libro a la vez, procesa una carpeta entera de EPUBs de forma secuencial, registrando el progreso de cada libro en un archivo de log para poder reanudar si el proceso se interrumpe. Esto no es directamente aplicable al bot de Telegram donde cada usuario procesa su propio libro, pero la logica de registro de progreso a nivel de archivo es mas robusta que la de jb41 porque separa claramente el estado del trabajo (que libro esta en proceso) del estado de la traduccion (que capitulos de ese libro estan completados).

La preservacion de estructura XML de este repo es tambien notable: en lugar de usar BeautifulSoup para parsear el HTML de los capitulos, usa el parser XML nativo de Python con lxml como backend para los fragmentos que son XHTML valido, y BeautifulSoup como fallback para los que son HTML mal formado. Este enfoque en dos niveles es mas correcto porque los EPUBs son tecnicamente XHTML, pero muchos editores producen XHTML que no es XML valido, y usar solo el parser XML falla en esos casos.

La mejora que sugiere este repo para el sistema de cache de la Fase 6 es usar el hash del fragmento junto con el nombre del idioma de destino como clave de cache, en lugar de solo el hash del texto. Esto permite que el mismo libro pueda traducirse a multiples idiomas sin que las traducciones se sobreescriban entre si.

---

## 11. Piotr-Grechuta/epub-translator-studio: interfaz de revision y sistema QA

Este repositorio tiene una arquitectura mas ambiciosa que los demas: no es solo un traductor sino un entorno de trabajo completo donde el usuario puede revisar y corregir cada traduccion antes de que se integre al EPUB final. Usa Python con Tkinter para la interfaz grafica y organiza el flujo de trabajo como un editor de pares: columna izquierda con el texto original, columna derecha con la traduccion editable.

El sistema QA automatico es la contribucion mas relevante para la reimplementacion. Antes de aceptar una traduccion, verifica automaticamente tres categorias de problemas. La primera categoria son inconsistencias de longitud: si la traduccion de un parrafo es menos de la mitad o mas del doble de la longitud del original en caracteres, es probable que el modelo haya omitido o duplicado contenido. La segunda son tokens mal formados: si el texto traducido contiene secuencias que parecen tokens sin restaurar, como corchetes con numeros, probablemente el modelo altero el formato de los placeholders. La tercera son terminaciones abruptas: si la ultima oracion del fragmento traducido no termina con signo de puntuacion, probablemente el modelo corto la respuesta antes de completarla.

Estas tres verificaciones pueden incorporarse como una capa de validacion en el restorer.py de la Fase 3, complementando la verificacion de tokens que ya existe, y aportando robustez adicional especialmente en fragmentos largos donde la probabilidad de error del modelo es mayor.

---

## 12. doubao-batch-translator: control de rate limiting y monitoreo de costos

Este repositorio resuelve un problema practico que los demas ignoran: los limites de velocidad de los proveedores de API no son solo en peticiones por segundo sino tambien en tokens por minuto, y superar cualquiera de los dos limites genera errores que interrumpen el proceso. La solucion implementa un sistema de throttling adaptativo que mide el tiempo entre peticiones y ajusta el delay automaticamente cuando detecta errores de rate limit, en lugar de usar un delay fijo que es siempre o muy conservador o insuficiente.

El monitoreo de costos es la otra contribucion relevante: este repo registra en un archivo CSV el costo de tokens de cada peticion, el proveedor usado, el timestamp, y el numero de caracteres del fragmento. Esto permite al usuario ver al final del proceso cuanto costo exactamente la traduccion y comparar costos entre proveedores. En el contexto del bot de Telegram, esta informacion podria mostrarse al usuario como resumen al final de la traduccion: cuantos tokens se consumieron, cuantos se ahorraron gracias a la cache, y una estimacion del costo en dolares basada en las tarifas publicas del proveedor.

El sistema de fallback entre proveedores es tambien notable: si Gemini devuelve un error de cuota agotada, el sistema automaticamente reintenta con DeepSeek, y vice versa. Esto requiere que el usuario haya configurado ambos proveedores, pero cuando eso se cumple el sistema nunca falla por falta de cuota en un proveedor especifico.

---

## 13. kakuyomu-translator: pipeline multiproveedores y exportacion multiformato

Este repositorio implementa un pipeline completo que va desde el scraping de fuentes de contenido japones hasta la exportacion a cuatro formatos de salida distintos: PDF, EPUB, Notion, y Obsidian. Para el presente proyecto lo relevante no es el scraping sino la arquitectura de exportacion y la seleccion de proveedor con fallback.

La exportacion a Notion y Obsidian es una idea que podria incorporarse como funcionalidad adicional en la Fase 8 o despues de ella. En el caso de Notion, la API publica permite crear paginas con bloques de texto estructurado a partir del contenido del EPUB, lo que produciria un libro de notas interactivo en lugar de un archivo estatico. En el caso de Obsidian, la exportacion produce archivos markdown enlazados que se integran con el sistema de notas del usuario y le permiten agregar anotaciones y marcadores junto al texto traducido.

La seleccion de proveedor con fallback de este repo es mas sofisticada que la del doubao: no solo hace fallback cuando hay error sino que evalua periodicamente la latencia de cada proveedor disponible y elige el mas rapido para las peticiones siguientes, de manera que si Gemini tiene latencia alta en ese momento, las peticiones van a DeepSeek hasta que la latencia se normalice.

---

## 14. comic-translate: procesamiento de formatos con contenido visual

Este repositorio traduce comics y manga en formatos CBZ, CBR, PDF, y EPUB, y su contribucion mas interesante para el presente proyecto no es el OCR sino la logica de decision sobre que elementos de una pagina contienen texto traducible. Para comics, eso requiere detectar globos de dialogo y caja de texto dentro de imagenes. Para EPUBs de texto normal, es mucho mas simple, pero el patron arquitectonico de clasificacion de elementos antes de traducir es el mismo que ya implementa el html_cleaner.py de la Fase 3.

Lo que es relevante de este repo para la Fase 7 es su manejo de formatos CBZ y CBR, que son archives ZIP y RAR de imagenes respectivamente. Si en el futuro se quiere expandir el bot para traducir comics en formato digital, el conversor de Calibre puede convertir CBZ a EPUB con las imagenes embebidas, y si las imagenes tienen texto, podria integrarse un motor de OCR como Tesseract para extraer ese texto antes de enviarlo al proveedor de traduccion.

---

## 15. teletrans: bot de Telegram con preferencias por usuario y streaming

Este repositorio implementa un bot de Telegram para traduccion de mensajes de texto en tiempo real usando OpenAI y DeepL, y su contribucion mas relevante es el sistema de preferencias por usuario. En lugar de una configuracion global del bot, cada usuario puede tener su idioma de destino preferido, su proveedor preferido, y su historial de traducciones almacenados de forma persistente en una base de datos SQLite.

En el presente proyecto, el estado FSM de aiogram se guarda en MemoryStorage, lo que significa que si el bot se reinicia, el estado de todos los usuarios se pierde. Para un bot de uso personal esto es aceptable porque hay pocos usuarios y la perdida de estado solo significa que hay que reenviar el archivo. Pero si en el futuro el bot se expone a multiples usuarios, migrar el almacenamiento de MemoryStorage a una base de datos SQLite usando la clase SqliteStorage de aiogram, que tiene exactamente la misma interfaz que MemoryStorage y no requiere cambiar ningun handler, resolveria este problema con un cambio minimo.

El streaming de respuestas que implementa teletrans, donde el mensaje de Telegram se actualiza caracter a caracter mientras el modelo genera la traduccion, es tecnica y visualmente atractivo pero tiene un costo importante en rate limit de edicion de mensajes de Telegram. Para fragmentos cortos de texto de mensaje es viable. Para capitulos de libro donde la generacion tarda minutos, el progreso por porcentaje de capitulos completados que ya implementa el progress.py de la Fase 1 es mas apropiado y mas informativo.

---

## 16. flibusta-bot: gestion de biblioteca y entrega por email

Este repositorio implementa un bot de Telegram que accede a un archivo de EPUBs, permite buscarlos por titulo y autor, y los envia al usuario por email o directamente como archivo en el chat. Su arquitectura no es directamente aplicable al presente proyecto porque el presente bot recibe archivos del usuario en lugar de gestionarlos, pero sus dos contribuciones conceptuales son relevantes.

La primera es el sistema de indexacion: cuando el usuario sube un archivo, el bot extrae los metadatos y los guarda en un registro persistente que permite mostrar al usuario un historial de traducciones anteriores. Si el usuario sube el mismo libro de nuevo, el bot puede detectarlo por el hash del archivo y ofrecerle la version ya traducida en lugar de volver a procesar.

La segunda es el envio por email como alternativa a la descarga directa en Telegram. Telegram tiene un limite de 50 MB para archivos enviados en chats privados, y algunos libros traducidos con imagenes embebidas pueden superar ese limite. Ofrecer el envio por email como fallback para archivos grandes es una funcionalidad de calidad de vida que resolveria este caso sin necesidad de comprimir el EPUB o escalar a una infraestructura de almacenamiento externo.

---

## Sintesis tecnica: que tomar de cada fuente

De quantrancse se toman los conceptos de recorrido del OPF para determinar el orden de archivos, preservacion de la jerarquia de carpetas al reempaquetar, y el sistema de glosario como mapa de sustitucion mejorado a inyeccion en el system prompt. De slyh se toman los conceptos de conversion HTML a texto plano por tipo de fragmento, prompts diferenciados segun la naturaleza del contenido, y el sistema de acumulacion hasta umbral. De oomol-lab se toman los conceptos de agrupacion por tokens estimados, cache de traducciones en disco, concurrencia controlada con semaforo, modos de salida, y callbacks de progreso para el bot. De jb41 se toman los conceptos de estado de trabajo por capitulo, reanudacion desde punto de interrupcion, y listado previo de capitulos con estimacion de costo. De Mubumbutu se toma el sistema de placeholders numerados para tags HTML inline, con mapa de sustitucion y restauracion post-traduccion. De hydropix se toma la arquitectura de providers intercambiables con interfaz abstracta comun. De KazKozDev se toma el concepto de segunda pasada de revision como modo opcional de calidad. De Calibre se toma la conversion de formatos, la escritura de metadatos post-traduccion, el analisis previo del archivo, y la deteccion de DRM.

Del segundo ciclo de analisis se incorporan adicionalmente: la normalizacion de encoding antes de parsear de ebook-GPT-translator, el parser en dos niveles XML y BeautifulSoup de al-nemirov, las verificaciones de QA automatico de Piotr-Grechuta, el throttling adaptativo y el monitoreo de costos de doubao-batch-translator, el fallback por latencia entre proveedores de kakuyomu, el sistema de preferencias persistentes por usuario de teletrans, y la deteccion de libros duplicados por hash de flibusta-bot.

Todo lo anterior se implementa desde cero en Python, sin copiar ningun codigo de estos repositorios, usando sus soluciones como referencia conceptual y mejoran-dolas en los puntos donde cada uno tenia limitaciones.

---

## Parte 1: preparacion del entorno y creacion del repositorio

### Herramientas que deben estar instaladas antes de comenzar

Python 3.11 o superior, porque la libreria aiogram en su version 3 requiere soporte de anotaciones de tipo modernas y de asyncio con la API de alto nivel que se estabilizo en esa version. Git, para el control de versiones local y la sincronizacion con GitHub. La interfaz de linea de comandos de GitHub, conocida como gh CLI, que permite crear repositorios remotos directamente desde la terminal sin necesidad de usar el navegador. Calibre, que debe instalarse como aplicacion del sistema porque se usa exclusivamente a traves de sus ejecutables de consola, a saber ebook-convert y ebook-meta, y no a traves de su API de plugins. En Windows, Calibre agrega automaticamente sus ejecutables al PATH del sistema durante la instalacion, lo que permite invocarlos desde cualquier terminal sin configuracion adicional.

### Flujo de trabajo con GitHub

A partir de la Fase 2, el flujo de trabajo recomendado es crear una rama separada para cada fase, desarrollar en esa rama, y hacer merge a main cuando la fase este completa y verificada. Esto permite revisar el historial de cambios por fase, revertir una fase entera si algo sale mal, y mantener la rama main siempre en un estado funcional, de manera que cualquier persona que clone el repositorio en cualquier momento tenga siempre una version operativa del codigo:

    git checkout -b fase-N-nombre
    git add .
    git commit -m "fase N: descripcion"
    git push -u origin fase-N-nombre
    gh pr create --title "Fase N" --body "descripcion"
    gh pr merge --squash

El flag --squash comprime todos los commits de la rama en uno solo en main, lo que mantiene el historial limpio y legible. Cada entrada en el historial de main corresponde a una fase completa del proyecto.

---

## Parte 2: estructura de directorios del proyecto

La organizacion del codigo en carpetas sigue el principio de separacion de responsabilidades, de forma que cada modulo tenga una funcion unica y bien delimitada, sin mezclar la logica de procesamiento de archivos con la logica de comunicacion con la API de traduccion ni con la logica de interaccion con el usuario en el bot. Esta disposicion permite que cada capa del sistema sea reemplazable de forma independiente: si en el futuro se cambia el proveedor de traduccion, solo se toca el modulo translation; si se cambia el framework del bot de aiogram a otra libreria, solo se toca el modulo bot; si se agrega soporte para otro formato de entrada ademas de EPUB, solo se toca el modulo epub o se agrega uno nuevo al mismo nivel.

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

## Parte 3: Fase 1, el esqueleto del proyecto (implementada)

Esta es la primera fase que se sube al repositorio. El objetivo es tener un proyecto Python funcional, con las dependencias declaradas, la configuracion de variables de entorno lista, y el bot de Telegram respondiendo al comando /start, aunque todavia sin ninguna logica de traduccion. Esta fase establece los cimientos arquitectonicos que todas las fases siguientes asumen como existentes.

### Dependencias

    aiogram==3.10.0
    google-generativeai==0.7.0
    openai==1.40.0
    beautifulsoup4==4.12.3
    lxml==5.2.2
    python-dotenv==1.0.1
    aiofiles==23.2.1
    httpx==0.27.0

aiogram es el framework asincrono para bots de Telegram, elegido sobre python-telegram-bot por su soporte nativo de asyncio y su sistema de filtros y routers que escala bien. google-generativeai es el SDK oficial de Google para acceder a Gemini. openai se usa para DeepSeek porque DeepSeek expone una API compatible con el protocolo de OpenAI, lo que significa que el mismo cliente puede usarse apuntando a un base_url diferente sin ningun cambio de codigo. beautifulsoup4 con el parser lxml es el conjunto estandar para manipular HTML en Python de forma robusta. aiofiles permite leer y escribir archivos de forma no bloqueante dentro del loop de asyncio del bot, lo cual es esencial para no detener el bot mientras se lee un EPUB grande del disco.

### Decisiones de diseno tomadas en la Fase 1

El almacenamiento FSM usa MemoryStorage, que es correcto para desarrollo y para uso personal con pocos usuarios concurrentes. El orden de registro de routers en el Dispatcher importa: start.router se registra primero porque sus comandos /start y /cancel deben tener prioridad sobre cualquier otro handler. Los comandos /start, /help, y /cancel se registran en la API de Telegram usando set_my_commands, lo que hace que aparezcan en el menu desplegable cuando el usuario escribe / en el chat. El modo skip_updates=True al iniciar el polling descarta los mensajes que llegaron mientras el bot estaba apagado, evitando reprocessar archivos de sesiones anteriores que ya no tienen estado FSM en el proceso actual.

### Mejoras identificadas para la Fase 1 basadas en el analisis ampliado

La migracion de MemoryStorage a SqliteStorage de aiogram eliminaria la perdida de estado FSM ante reinicios del bot, con un cambio de una sola linea en bot/main.py porque la interfaz es identica. La adicion de un sistema de preferencias por usuario, similar al de teletrans, persistiria el idioma de destino preferido y el proveedor favorito de cada usuario en SQLite, de manera que el usuario no necesite reconfigurar en cada sesion. La deteccion de duplicados por hash SHA256 del archivo recibido, inspirada en flibusta-bot, permitiria al bot reconocer cuando el usuario sube el mismo libro por segunda vez y ofrecerle la version ya traducida en lugar de reprocesar.

---

## Parte 4: Fase 2, el lector de EPUB (implementada)

Esta fase implementa el modulo epub/reader.py, que es el corazon del parser, y es la que mas atencion requiere a los detalles del formato EPUB porque todos los pasos posteriores dependen de que el lector entienda correctamente la estructura interna del archivo.

### Como funciona internamente un EPUB

Un archivo EPUB es un ZIP renombrado con extension .epub. Dentro de ese ZIP existe siempre un archivo llamado mimetype en la raiz, una carpeta META-INF que contiene container.xml, el cual apunta a la ubicacion del archivo OPF dentro del ZIP. El OPF puede estar en cualquier carpeta dependiendo de como el editor construyo el libro. El OPF contiene tres secciones fundamentales: metadata con el titulo, autor, idioma y otros campos, manifest que lista todos los archivos del libro con sus identificadores y tipos MIME, y spine que define el orden de lectura de los items del manifest.

El lector hace estas operaciones en orden. Primero, abrir el archivo como ZIP. Segundo, leer META-INF/container.xml y extraer el atributo full-path del elemento rootfile, que da la ruta al OPF. Tercero, parsear el manifest para construir un diccionario que mapea cada id de item a su href relativo y a su media-type. Cuarto, leer el spine y extraer la lista de idrefs en orden. Quinto, para cada archivo HTML calcular su ruta absoluta dentro del ZIP combinando el directorio base del OPF con el href relativo del item.

### Casos borde manejados en la implementacion

Los EPUBs con rutas que incluyen ../ en los hrefs del manifest se normalizan correctamente usando PurePosixPath. Los items del spine con atributo linear="no" se excluyen porque son paginas auxiliares que los lectores pueden mostrar opcionalmente pero que no forman parte de la secuencia principal de lectura. La ausencia de META-INF/container.xml se detecta antes de intentar parsear y produce un mensaje de error explicito sobre DRM potencial, en lugar de una excepcion criptica de zipfile. El archivo OPF puede estar en la raiz del ZIP o en cualquier subcarpeta, y la logica de calculo del directorio base del OPF maneja ambos casos correctamente.

### Mejoras identificadas para la Fase 2 basadas en el analisis ampliado

La normalizacion de encoding sugerida por ebook-GPT-translator puede incorporarse en el metodo read_chapter de EpubBook, detectando el charset declarado en el meta tag del HTML antes de decodificar, de manera que los capitulos con codificacion ISO-8859-1 declarada se decodifiquen correctamente en lugar de asumir siempre UTF-8. El parser en dos niveles de al-nemirov, que intenta primero XML y cae a BeautifulSoup si falla, mejoraria el manejo de EPUBs con XHTML mal formado que actualmente se procesan directamente con BeautifulSoup en la Fase 3 sin intentar el parser mas estricto primero. La claves de cache de la Fase 6 deberian incluir el idioma de destino como sugiere al-nemirov, para permitir traducir el mismo libro a multiples idiomas sin conflicto.

---

## Parte 5: Fase 3, la limpieza de HTML y el sistema de placeholders (implementada)

Esta es la fase mas delicada del proyecto porque define como se comunica el parser de HTML con el motor de traduccion. El error que cometen los sistemas simples es enviar HTML directamente al modelo de lenguaje, lo cual produce resultados inconsistentes porque el modelo a veces preserva los tags, a veces los altera, a veces los omite, y a veces confunde el contenido de los atributos con el texto que debe traducir.

### El sistema de placeholders implementado

El modulo epub/html_cleaner.py recibe un objeto BeautifulSoup que representa un parrafo o bloque de texto, recorre el arbol de nodos clasificando cada elemento, y produce un CleanResult que contiene el texto tokenizado, el mapa de restauracion, la clasificacion del fragmento como "plain", "with_tokens" o "complex", y las marcas de apertura y cierre del elemento raiz. Los tags inline como em, strong, span y a se reemplazan por pares de tokens [T01]/[/T01] guardando en el mapa la serializacion exacta del tag de apertura con todos sus atributos. Los elementos no traducibles como img, code, pre y script se reemplazan por tokens de posicion [P01] guardando el elemento completo con su contenido. Los comentarios HTML se tratan como tokens de posicion porque algunos EPUBs los usan como marcadores internos.

El modulo epub/html_restorer.py realiza el proceso inverso: detecta los tokens presentes y ausentes en el texto traducido mediante una expresion regular, registra advertencias para los tokens omitidos por el modelo, reemplaza todos los tokens encontrados por su HTML original usando el mapa, y elimina cualquier token residual no reconocido que el modelo haya generado por su cuenta. La funcion count_token_mismatches permite a la capa de traduccion decidir si reintentar la traduccion de un fragmento basandose en el porcentaje de tokens omitidos. La funcion should_skip filtra elementos vacios antes de que lleguen al limpiador, evitando llamadas innecesarias al proveedor.

### Mejoras identificadas para la Fase 3 basadas en el analisis ampliado

Las verificaciones de QA automatico de Piotr-Grechuta deberian incorporarse como una funcion validate_translation en html_restorer.py que compruebe tres condiciones adicionales: si la relacion de longitud entre traduccion y original es anormal (menor de 0.4 o mayor de 2.5 veces), si la respuesta contiene corchetes con numeros que sugieren tokens no restaurados, y si la ultima oracion del texto traducido no termina con signo de puntuacion lo que sugiere truncamiento. Un sistema de tokens con nombre semantico, como [EM01] para em y [STRONG01] para strong, daria al modelo informacion adicional sobre la funcion de cada tag y podria mejorar la calidad de la traduccion en fragmentos con multiples tipos de enfasis, aunque el costo en tokens de contexto es mayor. La inyeccion de terminos de glosario como tokens especiales [TERM01] antes de la tokenizacion, sugerida por el analisis de Mubumbutu, es una mejora concreta para la Fase 8 que puede implementarse sin cambiar la interfaz publica del cleaner.

---

## Parte 6: Fase 4, los proveedores de traduccion

La clase base abstracta en translation/base.py define la interfaz con tres elementos: el metodo asincrono translate que recibe texto y system prompt y devuelve texto traducido, el metodo estimate_tokens que usa la aproximacion de un token por cada cuatro caracteres en texto latino y un token por cada dos caracteres en texto japones o chino, y la propiedad name que identifica el proveedor. Esta abstraccion garantiza que el codigo de procesamiento del EPUB nunca depende directamente de ningun proveedor y que agregar un nuevo proveedor en el futuro solo requiere crear una nueva clase sin modificar ningun modulo existente.

gemini.py implementa esta interfaz usando generate_content_async del SDK de Google con temperatura 0.3, que produce traducciones consistentes y menos creativas, usando el modelo gemini-2.5-flash-preview que tiene un free tier generoso al momento de redactar este documento. deepseek.py implementa la misma interfaz usando el cliente openai apuntando a api.deepseek.com/v1 con el modelo deepseek-chat, que es el mas economico del catalogo de DeepSeek y tiene buena relacion entre costo y calidad para traduccion directa.

grouper.py acumula fragmentos hasta alcanzar 4000 tokens por grupo antes de enviarlos al proveedor. El valor de 4000 tokens por grupo deja margen para el system prompt y la respuesta sin acercarse a los limites del modelo, aunque para Gemini 2.5 Flash con un contexto de un millon de tokens este umbral puede aumentarse significativamente para reducir el numero total de peticiones a la API.

### Mejoras identificadas para la Fase 4 basadas en el analisis ampliado

El throttling adaptativo de doubao-batch-translator deberia incorporarse como una clase RateLimiter en translation/base.py que cada proveedor instancia con sus limites especificos de RPM y TPM, de manera que el sistema ajuste automaticamente el delay entre peticiones cuando detecta errores 429 del proveedor en lugar de fallar. El monitoreo de costos puede implementarse como un registro simple en state/job.py que acumule el conteo de tokens input y output de cada peticion y los muestre al usuario como resumen al final de la traduccion, calculando el costo estimado en dolares usando las tarifas publicas del proveedor almacenadas en config.py. El fallback automatico entre proveedores cuando uno devuelve error de cuota, inspirado en doubao-batch-translator, requiere que el job conozca todos los proveedores disponibles y los itere en orden de preferencia ante cada error de cuota.

---

## Parte 7: Fase 5, el bot de Telegram

El handler upload.py descarga el archivo al directorio downloads/ con nombre unico generado con uuid4, extrae la extension, y si no es EPUB llama al conversor de Calibre antes de continuar, devolviendo un error explicito al usuario si el formato no es soportado. El bot responde con un mensaje de confirmacion que muestra el titulo del libro, el autor, el formato detectado, y el numero aproximado de capitulos extraidos del spine del OPF. Luego muestra un teclado inline con tres opciones: configurar opciones, ver lista de capitulos, o traducir directamente con la configuracion por defecto.

El handler settings.py guia al usuario por cuatro pantallas sucesivas: seleccion de idioma con las opciones mas comunes como idioma, seleccion del proveedor de traduccion disponible segun las claves configuradas, seleccion del modo de salida, y seleccion del nivel de calidad. Al final de cada flujo muestra un resumen de toda la configuracion antes de pedir confirmacion, leyendo los valores del estado FSM para garantizar que lo que se muestra es exactamente lo que se usara.

El handler progress.py implementa el mecanismo de actualizacion del mensaje de estado respetando el rate limit de Telegram de una edicion por segundo por chat, usando asyncio.Lock para evitar ediciones concurrentes y time.monotonic para medir el intervalo minimo entre ediciones. El mensaje de progreso incluye una barra de progreso construida con caracteres Unicode que muestra visualmente el porcentaje completado junto con el numero de capitulo actual y el total.

### Mejoras identificadas para la Fase 5 basadas en el analisis ampliado

La lista de capitulos deberia incluir la estimacion de palabras por capitulo que ya calcula el reader.py de la Fase 2, permitiendo al usuario ver cuales capitulos son cortos y cuales son largos antes de confirmar. La seleccion de rango de capitulos, donde el usuario puede indicar "traducir del capitulo 3 al 7", requiere agregar un handler adicional al flujo de configuracion que lea los indices seleccionados y los guarde en el estado FSM para que el job de la Fase 6 los use como filtro. El envio por email como fallback para archivos grandes, sugerido por flibusta-bot, puede implementarse como una opcion opcional en la pantalla de confirmacion cuando el EPUB estimado supera los 45 MB.

---

## Parte 8: Fase 6, la cache y la reanudacion

El modulo state/cache.py nombra cada entrada de cache con el hash SHA256 del texto original calculado con hashlib, mas el codigo de idioma de destino, de manera que el mismo fragmento puede estar traducido a varios idiomas sin conflicto de claves. Antes de enviar cualquier fragmento al proveedor, el sistema busca en la cache. Si existe, usa el resultado del disco sin hacer ninguna llamada a la API. Si no existe, llama al proveedor, guarda el resultado en la cache, y continua.

El modulo state/job.py mantiene el estado del proceso a nivel de capitulo con tres estados posibles: pending, in_progress, y completed. El estado se guarda en un archivo JSON en el directorio del job, de manera que si el bot se reinicia en medio de una traduccion, al retomar el mismo archivo el job puede cargar ese estado y saltar los capitulos ya completados. Al completar todos los capitulos, el job elimina el archivo de estado y el directorio temporal, liberando espacio en disco.

### Mejoras identificadas para la Fase 6 basadas en el analisis ampliado

La deteccion de libros duplicados por hash del archivo recibido, sugerida por flibusta-bot, puede implementarse en state/job.py calculando el SHA256 del archivo de entrada al crear el job y buscando si ya existe un directorio de job con el mismo hash y el mismo idioma de destino que ya este en estado completado, caso en el cual se salta todo el proceso y se envia directamente el EPUB ya traducido. El registro de costos sugerido por doubao-batch-translator puede guardarse en el mismo archivo JSON del job como una lista de entradas con timestamp, proveedor, tokens de entrada, y tokens de salida, y al final del job calcularse el total y mostrarse al usuario.

---

## Parte 9: Fase 7, la integracion con Calibre

calibre/converter.py usa asyncio.create_subprocess_exec para no bloquear el event loop del bot mientras Calibre hace la conversion, que puede tomar varios segundos en libros con muchas imagenes embebidas. Si ebook-convert devuelve un codigo de salida distinto de cero, el modulo captura el stderr y lo incluye en el mensaje de error que se muestra al usuario. La deteccion del formato de entrada se hace por la extension del archivo recibido: si la extension es .epub no se hace ninguna conversion, y si es .mobi, .azw3, .fb2, .rtf, o .docx se convierte antes de procesar.

calibre/metadata.py implementa dos funciones. La primera, read_metadata, ejecuta ebook-meta sobre el archivo y parsea la salida de texto plano para extraer titulo, autor, idioma, editorial, y serie. La segunda, write_metadata, ejecuta ebook-meta con los flags correspondientes para actualizar esos campos en el EPUB de salida, cambiando el idioma al codigo BCP 47 del idioma de destino y agregando el sufijo de traduccion al titulo.

La deteccion de DRM se hace verificando la presencia y legibilidad de META-INF/container.xml antes de intentar procesar el archivo. Si el archivo tiene DRM, el ZIP puede abrirse pero container.xml no existe o tiene contenido cifrado, y el sistema informa al usuario con un mensaje claro en lugar de fallar con una excepcion de zipfile que el usuario no sabria interpretar.

### Mejoras identificadas para la Fase 7 basadas en el analisis ampliado

El soporte para formatos CBZ y CBR de comics, sugerido por comic-translate, puede incorporarse en converter.py como un caso especial donde Calibre convierte el archivo a EPUB y el lector de la Fase 2 lo procesa normalmente, con la diferencia de que el EPUB resultante contendra las imagenes del comic como paginas y no tendra texto a traducir a menos que se integre un motor de OCR. La exportacion a Notion y Obsidian, sugerida por kakuyomu-translator, puede implementarse como backends alternativos en el packager de la Fase 2 que en lugar de producir un archivo ZIP producen llamadas a la API de Notion o archivos Markdown enlazados.

---

## Parte 10: Fase 8, las funcionalidades avanzadas

El modo bilingue expone tres opciones al usuario en el teclado de configuracion: reemplazar el texto original, agregar la traduccion en el mismo parrafo separada por un espacio, y agregar la traduccion como parrafo separado con una clase CSS diferente. El modo de salida bilingue-bloque es el mas util para lectores que quieren aprender el idioma mientras leen, porque pueden ver el original y la traduccion en paralelo sin que uno interfiera con la lectura del otro.

El modo de calidad aplica una segunda llamada al LLM que evalua unicamente tres aspectos del texto traducido: nombres propios incorrectamente traducidos, terminos del glosario no respetados, y frases que suenan mecanicas o poco naturales en el idioma de destino. Si no detecta ningun problema en ninguno de los tres aspectos, devuelve la traduccion original sin modificacion, con lo cual el costo adicional en ese fragmento es solo el de los tokens del prompt de evaluacion, que es mucho menor que el de la traduccion completa.

El glosario se inyecta directamente en el system prompt de cada llamada al modelo, lo que permite al modelo usarlo de forma contextualmente coherente en lugar de aplicar una sustitucion ciega posterior. La seccion del prompt que describe el glosario tiene la forma "las siguientes palabras o frases no deben traducirse: [lista de terminos], y las siguientes palabras deben traducirse siempre como se indica: [lista de pares original-traduccion]", de manera que el modelo puede respetar el glosario incluso cuando los terminos aparecen en construcciones gramaticales complejas o con morfologia variable.

### Mejoras identificadas para la Fase 8 basadas en el analisis ampliado

El sistema de QA automatico de Piotr-Grechuta puede incorporarse como una verificacion adicional dentro del modo de calidad, donde antes de la segunda pasada del LLM se ejecutan las verificaciones automaticas de longitud, tokens residuales, y terminacion abrupta, y solo se llama al LLM para la evaluacion si alguna de esas verificaciones falla. Esto reduce el costo del modo de calidad cuando el fragmento ya paso las verificaciones simples. Un sistema de estadisticas de uso, inspirado en teletrans, puede agregarse en este punto del desarrollo: al finalizar cada traduccion, el bot muestra al usuario el tiempo total, el numero de capitulos procesados, los tokens consumidos, el porcentaje de cache hits, y el costo estimado en dolares, de forma que el usuario tenga una vision clara del valor que aporta el sistema.

---

## Ideas de funcionalidades adicionales mas alla de la Fase 8

Este apartado recoge las ideas surgidas del segundo ciclo de analisis que no encajan en ninguna de las ocho fases actuales pero que pueden implementarse despues de completar la Fase 8 sin necesidad de modificar la arquitectura existente, porque cada una se agrega como un modulo nuevo o como una extension de un modulo existente.

La primera idea es el sistema de roles de usuario, donde el usuario que instala el bot para uso personal tiene acceso completo a todas las opciones, mientras que si el bot se comparte con otros usuarios, el administrador puede configurar limites de uso por usuario como numero maximo de libros por dia o idiomas permitidos. Esto requiere una base de datos SQLite con una tabla de usuarios y una tabla de limites, mas un conjunto de handlers adicionales para el panel de administracion.

La segunda idea es la exportacion a Notion y Obsidian, donde el usuario puede elegir recibir el libro traducido no como archivo EPUB sino como una coleccion de paginas en Notion o como una carpeta de archivos Markdown enlazados. Esto es especialmente util para usuarios que usan Notion como sistema de notas porque pueden anotar directamente sobre el texto traducido sin necesidad de un lector de ebooks externo.

La tercera idea es la integracion con servicios de almacenamiento en la nube como Google Drive o Dropbox, donde el EPUB traducido se sube automaticamente a la carpeta del usuario en lugar de enviarse como archivo en Telegram, lo que evita el limite de 50 MB de Telegram y permite al usuario acceder al libro desde cualquier dispositivo sin necesidad de descargarlo desde el chat.

La cuarta idea es el soporte para comics en formatos CBZ y CBR con OCR integrado, donde el conversor de Calibre convierte el archivo a EPUB con las imagenes del comic, luego un motor de OCR como Tesseract extrae el texto de los globos de dialogo, ese texto pasa por el pipeline normal de limpieza y traduccion, y finalmente se superpone sobre las imagenes originales en las posiciones detectadas por el OCR. Este flujo requiere trabajo adicional en el modulo epub/ pero no cambia ninguno de los modulos de traduccion ni de interaccion con el usuario.

---

## Verificacion end-to-end

Iniciar el bot con el comando python -m bot.main y verificar que no haya errores en la salida de la terminal, en particular que config.py haya encontrado TELEGRAM_BOT_TOKEN y que se hayan creado los directorios translations_cache/ y downloads/. Abrir Telegram y enviar /start al bot, verificando que responda con el mensaje de bienvenida que muestra las instrucciones de uso. Subir un EPUB de prueba, preferiblemente un libro corto de dominio publico disponible en el Proyecto Gutenberg, y seguir el flujo completo de configuracion: seleccionar idioma, seleccionar proveedor, elegir modo de salida, confirmar.

Verificar que el mensaje de progreso se actualice correctamente durante la traduccion y que la barra de progreso avance a medida que se completan los capitulos. Descargar el EPUB de salida y abrirlo en un lector compatible como Calibre, Foliate, o el lector de Kobo, verificando que el texto este en el idioma de destino, que la tabla de contenidos funcione correctamente y lleve a los capitulos correspondientes, y que las imagenes y el formato del texto se hayan preservado sin corrupcion.

Interrumpir el proceso a la mitad de una traduccion, reiniciar el bot, subir el mismo archivo, y verificar que el sistema retome desde el capitulo donde se detuvo sin retraducir los anteriores. Verificar que el segundo archivo producido es identico al que se habria producido sin la interrupcion, comparando el contenido de los capitulos ya traducidos antes de la interrupcion con los del archivo final.

Probar tambien el caso de un archivo en formato MOBI o AZW3 para verificar que la conversion de Calibre funciona correctamente y que el EPUB resultante se procesa igual que uno recibido directamente en formato EPUB. Probar el caso de un archivo con DRM verificando que el bot responde con un mensaje de error explicito que menciona la proteccion digital, en lugar de fallar con una excepcion no controlada.
