"""
Persistencia de preferencias por usuario y registro de traducciones completadas.

Este modulo gestiona dos tablas en la misma base de datos SQLite. La primera,
user_prefs, guarda el idioma de destino preferido y el proveedor de traduccion
favorito de cada usuario, de manera que en cada nueva sesion el bot pre-rellena
la configuracion con los valores que el usuario eligio la ultima vez, sin que
tenga que reconfigurar manualmente. La segunda, translation_history, registra
el hash SHA256 de cada archivo ya traducido junto con el idioma de destino y la
ruta del EPUB de salida, lo que permite detectar cuando el usuario sube el mismo
libro por segunda vez y ofrecerle la version ya traducida sin reprocesar.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Optional

import config


class UserPrefs:
    """
    Interfaz de acceso a las tablas user_prefs y translation_history en SQLite.

    Todas las operaciones de escritura se serializan a traves de un asyncio.Lock
    compartido por la instancia para evitar conflictos de escritura concurrente.
    Las lecturas no requieren bloqueo porque SQLite permite multiples lectores
    concurrentes cuando no hay escrituras en curso.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._write_lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_prefs (
                    user_id         INTEGER PRIMARY KEY,
                    target_language TEXT    NOT NULL DEFAULT 'es',
                    provider        TEXT
                )
            """)
            # La clave primaria compuesta (file_hash, target_language) garantiza
            # que se puede traducir el mismo libro a varios idiomas y cada par
            # queda registrado de forma independiente sin que se sobreescriban.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translation_history (
                    file_hash       TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    output_path     TEXT NOT NULL,
                    PRIMARY KEY (file_hash, target_language)
                )
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Preferencias de usuario

    def _get_prefs_sync(self, user_id: int) -> Optional[tuple]:
        with sqlite3.connect(self._db_path) as conn:
            return conn.execute(
                "SELECT target_language, provider FROM user_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchone()

    def _save_prefs_sync(self, user_id: int, target_language: str, provider: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_prefs (user_id, target_language, provider) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    target_language = excluded.target_language,
                    provider        = excluded.provider
                """,
                (user_id, target_language, provider),
            )
            conn.commit()

    async def get_prefs(self, user_id: int) -> dict:
        """
        Devuelve las preferencias del usuario, o los valores por defecto del sistema
        si el usuario nunca ha completado una sesion de configuracion. El proveedor
        por defecto es el primero de la lista de proveedores disponibles segun las
        claves de API configuradas en el .env, o None si no hay ninguno.
        """
        row = await asyncio.to_thread(self._get_prefs_sync, user_id)
        default_provider = config.AVAILABLE_PROVIDERS[0] if config.AVAILABLE_PROVIDERS else None
        if row:
            return {
                "target_language": row[0],
                "provider": row[1] or default_provider,
            }
        return {
            "target_language": config.DEFAULT_TARGET_LANGUAGE,
            "provider": default_provider,
        }

    async def save_prefs(self, user_id: int, target_language: str, provider: str) -> None:
        """Persiste el idioma y el proveedor elegidos por el usuario en esta sesion."""
        async with self._write_lock:
            await asyncio.to_thread(
                self._save_prefs_sync, user_id, target_language, provider
            )

    # -------------------------------------------------------------------------
    # Historial de traducciones completadas (deteccion de duplicados)

    def _get_history_sync(self, file_hash: str, target_language: str) -> Optional[str]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT output_path FROM translation_history "
                "WHERE file_hash = ? AND target_language = ?",
                (file_hash, target_language),
            ).fetchone()
            return row[0] if row else None

    def _save_history_sync(
        self, file_hash: str, target_language: str, output_path: str
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO translation_history (file_hash, target_language, output_path)
                VALUES (?, ?, ?)
                ON CONFLICT(file_hash, target_language) DO UPDATE SET
                    output_path = excluded.output_path
                """,
                (file_hash, target_language, output_path),
            )
            conn.commit()

    async def find_existing_translation(
        self, file_hash: str, target_language: str
    ) -> Optional[str]:
        """
        Busca si ya existe un EPUB traducido para el hash y el idioma dados.

        Devuelve la ruta del archivo de salida si existe y el archivo sigue en disco,
        o None si no hay registro o si el archivo fue eliminado. La verificacion de
        existencia en disco es necesaria porque la ruta guardada puede haber quedado
        obsoleta si el directorio de descargas se limpio manualmente.
        """
        path = await asyncio.to_thread(
            self._get_history_sync, file_hash, target_language
        )
        if path and Path(path).exists():
            return path
        return None

    async def register_translation(
        self, file_hash: str, target_language: str, output_path: str
    ) -> None:
        """
        Registra un EPUB traducido en el historial para su deteccion futura.

        Este metodo se llama al finalizar exitosamente una traduccion. La ruta
        del archivo de salida se guarda de forma absoluta para que find_existing_translation
        pueda verificar su existencia independientemente del directorio de trabajo actual.
        """
        async with self._write_lock:
            await asyncio.to_thread(
                self._save_history_sync, file_hash, target_language, str(Path(output_path).resolve())
            )


# Instancia global del modulo para evitar multiples conexiones a la misma base de
# datos desde distintos handlers. Se inicializa la primera vez que se importa el
# modulo, antes de que el bot comience a recibir mensajes.
_instance: Optional[UserPrefs] = None


def get_user_prefs() -> UserPrefs:
    """
    Devuelve la instancia singleton de UserPrefs, creandola si es la primera llamada.

    La base de datos se almacena junto con el resto de los archivos de estado del
    sistema en TRANSLATIONS_CACHE_DIR para que la limpieza de ese directorio elimine
    tambien las preferencias y el historial en un solo paso.
    """
    global _instance
    if _instance is None:
        db_path = config.TRANSLATIONS_CACHE_DIR / "user_prefs.db"
        _instance = UserPrefs(db_path)
    return _instance
