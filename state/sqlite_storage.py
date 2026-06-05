"""
Almacenamiento FSM persistente en SQLite como reemplazo de MemoryStorage.

Su objetivo es que el estado de la conversacion de cada usuario sobreviva a los
reinicios del bot, de manera que si el servidor se cae en medio de un flujo de
configuracion el usuario no pierda lo que ya habia seleccionado y puede retomarlo
sin necesidad de volver a subir el archivo. La interfaz implementa exactamente los
mismos metodos abstractos de BaseStorage que usa MemoryStorage, de modo que el
cambio en bot/main.py se reduce a reemplazar una clase por la otra sin modificar
ningun handler ni ninguna otra parte del sistema.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey


class SqliteStorage(BaseStorage):
    """
    Implementacion de BaseStorage que persiste el estado FSM en una base de datos
    SQLite usando asyncio.to_thread para no bloquear el event loop del bot mientras
    el modulo sqlite3 de la biblioteca estandar de Python, que es sincrono, realiza
    las operaciones de lectura y escritura en disco.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._write_lock = asyncio.Lock()
        # La tabla se crea en el constructor para garantizar que existe antes de
        # que cualquier handler intente leer o escribir estado. El uso de
        # IF NOT EXISTS hace que la llamada sea idempotente y no falle si la
        # base de datos ya estaba inicializada de una sesion anterior del bot.
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_state (
                    storage_key  TEXT PRIMARY KEY,
                    state        TEXT,
                    data         TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.commit()

    @staticmethod
    def _build_key(key: StorageKey) -> str:
        # El thread_id es opcional en StorageKey y puede ser None en chats privados.
        # Se incluye en la clave compuesta para soportar correctamente los grupos
        # con hilos de Telegram sin modificar la estructura de la tabla.
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id}"

    def _get_row_sync(self, key: str) -> tuple[Optional[str], str]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT state, data FROM fsm_state WHERE storage_key = ?", (key,)
            ).fetchone()
            return (row[0], row[1]) if row else (None, "{}")

    def _upsert_state_sync(self, key: str, state: Optional[str]) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO fsm_state (storage_key, state, data) VALUES (?, ?, '{}')
                ON CONFLICT(storage_key) DO UPDATE SET state = excluded.state
                """,
                (key, state),
            )
            conn.commit()

    def _upsert_data_sync(self, key: str, data_json: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO fsm_state (storage_key, state, data) VALUES (?, NULL, ?)
                ON CONFLICT(storage_key) DO UPDATE SET data = excluded.data
                """,
                (key, data_json),
            )
            conn.commit()

    async def set_state(self, key: StorageKey, state: Optional[str] = None) -> None:
        """Persiste el estado FSM del usuario, preservando sus datos de sesion."""
        async with self._write_lock:
            await asyncio.to_thread(
                self._upsert_state_sync, self._build_key(key), state
            )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Recupera el estado FSM del usuario, devolviendo None si no existe registro."""
        state, _ = await asyncio.to_thread(self._get_row_sync, self._build_key(key))
        return state

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        """Persiste los datos de sesion del usuario, preservando su estado FSM."""
        async with self._write_lock:
            await asyncio.to_thread(
                self._upsert_data_sync, self._build_key(key), json.dumps(data)
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Recupera los datos de sesion del usuario, devolviendo un dict vacio si no existe."""
        _, data_json = await asyncio.to_thread(self._get_row_sync, self._build_key(key))
        return json.loads(data_json)

    async def close(self) -> None:
        # sqlite3 cierra la conexion al finalizar cada bloque with, de manera que
        # no hay conexiones persistentes que necesiten cerrarse explicitamente aqui.
        pass
