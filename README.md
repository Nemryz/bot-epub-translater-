# bot-epub-translater

Bot de Telegram para la traduccion de libros electronicos mediante modelos de lenguaje de gran escala, construido desde cero en Python con una arquitectura modular que separa cada responsabilidad en capas independientes y reemplazables.

---

## Que hace este proyecto

El sistema recibe un archivo de libro electronico directamente en el chat de Telegram, lo procesa internamente respetando la estructura original del EPUB, lo traduce al idioma que el usuario seleccione usando el proveedor de inteligencia artificial configurado, y devuelve el resultado como un archivo listo para abrir en cualquier lector de ebooks. El libro traducido conserva la tabla de contenidos, las imagenes, las hojas de estilo, los hiperenlaces internos y el orden de capitulos del original, sin alterar nada de la estructura que no sea el texto visible.

---

## Formatos de entrada aceptados

EPUB, MOBI, AZW3, FB2, RTF y DOCX. Los formatos que no son EPUB se convierten automaticamente a ese formato antes de procesarse, usando Calibre como conversor de sistema, y el resultado final se entrega igualmente como EPUB con los metadatos del libro actualizados para reflejar el idioma de destino.

---

## Proveedores de traduccion disponibles

Gemini 2.5 Flash, a traves del SDK oficial de Google, que ofrece un nivel gratuito con limites de uso generosos y un contexto de un millon de tokens que permite procesar capitulos enteros en una sola peticion. DeepSeek Chat, a traves del cliente de OpenAI apuntando al endpoint de DeepSeek, que es el proveedor mas economico del catalogo para traduccion en volumen. Ambos proveedores implementan la misma interfaz abstracta, de forma que agregar un nuevo proveedor en el futuro implica solo crear una clase nueva sin tocar el resto del sistema.

---

## Modos de salida

El usuario puede elegir entre tres modos antes de confirmar la traduccion. El modo reemplazar elimina el texto original y deja solo la traduccion en el lugar de cada parrafo. El modo bilingue inline agrega la traduccion inmediatamente despues del parrafo original en el mismo elemento HTML, separada por un espacio. El modo bilingue bloque inserta la traduccion como un parrafo nuevo a continuacion del original, con una clase CSS diferente para que los lectores que soporten estilos puedan distinguirlos visualmente, lo que lo convierte en el modo mas util para quienes quieren leer el original y la traduccion en paralelo.

---

## Nivel de calidad

El modo normal traduce cada grupo de fragmentos en una sola pasada al modelo. El modo de alta calidad aplica una segunda llamada al mismo modelo por cada grupo, enviando tanto el texto original como la traduccion generada y pidiendole que evalúe si hay nombres propios incorrectamente traducidos, terminos del glosario que no se respetaron, o frases que suenen poco naturales en el idioma de destino. Si no detecta ningun problema, la segunda pasada devuelve la traduccion sin cambios y el costo adicional se reduce al minimo. Si detecta algun problema, devuelve la version corregida.

---

## Requisitos del sistema

Python 3.11 o superior. Calibre instalado como aplicacion del sistema, accesible desde la terminal mediante los comandos ebook-convert y ebook-meta. Al menos una clave de API valida, ya sea de Google AI Studio para Gemini o de DeepSeek para su servicio de chat.

---

## Instalacion

Clonar el repositorio e instalar las dependencias:

    git clone https://github.com/TU_USUARIO/bot-epub-translater.git
    cd bot-epub-translater
    pip install -r requirements.txt

Copiar la plantilla de variables de entorno y completarla con las claves reales:

    cp .env.example .env

Editar el archivo .env con cualquier editor de texto y reemplazar los valores de ejemplo por las claves de API reales y el token del bot obtenido desde BotFather en Telegram.

Iniciar el bot:

    python -m bot.main

---

## Estructura del proyecto

    bot/              handlers de Telegram, teclados inline y punto de entrada principal
    epub/             parser de EPUB, sistema de placeholders HTML y reempaquetador
    translation/      providers de traduccion intercambiables y agrupador de fragmentos
    state/            cache de traducciones en disco y estado de trabajo por capitulo
    calibre/          wrappers de subprocess para ebook-convert y ebook-meta
    documents/        documentacion tecnica del proyecto, incluyendo el plan de arquitectura

---

## Variables de entorno

    TELEGRAM_BOT_TOKEN       token del bot obtenido desde BotFather
    GEMINI_API_KEY           clave de Google AI Studio (opcional si se usa DeepSeek)
    DEEPSEEK_API_KEY         clave de DeepSeek (opcional si se usa Gemini)
    DEFAULT_TARGET_LANGUAGE  idioma de destino por defecto, es por defecto
    MAX_CONCURRENT_REQUESTS  peticiones simultaneas a la API, 3 por defecto
    TRANSLATIONS_CACHE_DIR   directorio para la cache de traducciones en disco
    DOWNLOADS_DIR            directorio temporal para los archivos del usuario

---

## Fases de implementacion

El proyecto se construye en ocho fases incrementales, cada una con su propio commit en el repositorio, de forma que el historial refleja el avance progresivo del sistema. La documentacion completa de cada fase, incluyendo las decisiones de arquitectura, los conceptos tomados de los repositorios de referencia y las mejoras aplicadas, se encuentra en el archivo documents/plan-de-arquitectura.md dentro de este mismo repositorio.

---

## Licencia

MIT
