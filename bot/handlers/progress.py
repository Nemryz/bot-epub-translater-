"""
Utilidad para reportar el progreso de la traduccion al usuario en Telegram.

Telegram impone un limite de aproximadamente una edicion de mensaje por segundo por chat.
Este modulo encapsula esa restriccion con un lock asincrono y un registro del ultimo
momento de edicion, de manera que los modulos de traduccion pueden llamar a update()
con la frecuencia que quieran sin preocuparse por saturar la API de Telegram ni recibir
errores de rate limiting que interrumpiran el proceso.
"""

import time
import asyncio
from aiogram.types import Message

# El ancho de la barra de progreso en caracteres de bloque Unicode. Veinte caracteres
# es un tamaño que se ve bien en dispositivos moviles sin ocupar toda la linea.
PROGRESS_BAR_WIDTH = 20

# El intervalo minimo entre ediciones del mensaje de progreso, en segundos. Un valor
# de 1.2 da un margen de seguridad sobre el limite de un segundo de Telegram para
# evitar errores de rate limit incluso si hay pequenas variaciones en la latencia de red.
MIN_EDIT_INTERVAL = 1.2


class ProgressReporter:
    """
    Gestor de actualizaciones de progreso para una sesion de traduccion activa.

    Se instancia una vez por libro al inicio del proceso de traduccion y se pasa
    como argumento a la funcion que procesa los capitulos. Cada vez que se completa
    un capitulo, la funcion llama a update() con el numero de capitulos completados.
    ProgressReporter decide internamente si es momento de editar el mensaje o si
    debe esperar para no superar el rate limit de Telegram.
    """

    def __init__(self, message: Message, total_chapters: int) -> None:
        """
        Inicializa el reporter con el mensaje que se editara y el total de capitulos.

        El mensaje debe ser el que el bot envio al usuario al confirmar la traduccion,
        ya que ese es el que se edita repetidamente durante el proceso. total_chapters
        se usa para calcular el porcentaje de avance y la barra de progreso.
        """
        self._message = message
        self._total = total_chapters
        self._current = 0
        self._last_edit_at = 0.0
        # El lock garantiza que dos corrutinas de traduccion concurrentes no intenten
        # editar el mensaje al mismo tiempo, lo cual causaria condiciones de carrera
        # donde la segunda edicion sobreescribe a la primera con datos inconsistentes.
        self._lock = asyncio.Lock()

    async def update(self, completed_chapters: int) -> None:
        """
        Actualiza el contador de capitulos completados y edita el mensaje si corresponde.

        Si el intervalo desde la ultima edicion es menor que MIN_EDIT_INTERVAL, la
        actualizacion se descarta silenciosamente. Esto no es un problema porque la
        siguiente llamada a update() enviara el estado mas reciente, de manera que
        el usuario siempre ve el progreso actual y nunca un estado intermedio obsoleto.
        """
        async with self._lock:
            self._current = completed_chapters
            now = time.monotonic()
            if now - self._last_edit_at < MIN_EDIT_INTERVAL:
                return
            self._last_edit_at = now
            await self._edit()

    async def done(self) -> None:
        """
        Marca la traduccion como completada y edita el mensaje por ultima vez.

        Esta llamada no respeta el intervalo minimo de edicion porque es la actualizacion
        final y es importante que el usuario vea el estado de completado, independientemente
        de cuando ocurrio la ultima actualizacion de progreso intermedio.
        """
        self._current = self._total
        await self._edit()

    async def _edit(self) -> None:
        """
        Construye el texto de progreso y edita el mensaje en Telegram.

        El bloque try/except silencia las excepciones de edicion porque es posible que
        el mensaje haya sido eliminado por el usuario, que Telegram haya expirado la
        sesion, o que ocurra un error transitorio de red. En esos casos, lo correcto
        es continuar la traduccion en lugar de abortar todo el proceso por un fallo
        de presentacion que no afecta al resultado final.
        """
        pct = int(self._current / self._total * 100) if self._total else 0
        filled = int(PROGRESS_BAR_WIDTH * self._current / self._total) if self._total else 0
        bar = "█" * filled + "░" * (PROGRESS_BAR_WIDTH - filled)
        text = (
            f"Traduciendo...\n"
            f"{bar} {pct}%\n"
            f"Capitulo {self._current} de {self._total}"
        )
        try:
            await self._message.edit_text(text)
        except Exception:
            pass
