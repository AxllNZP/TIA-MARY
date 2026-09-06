"""
Almacen de sesiones en memoria para el pipeline conversacional.
Aisla el contexto (atributos heredados) y el historial de chat por session_id,
evitando que distintos usuarios de WhatsApp compartan estado.

Backend intercambiable: la interfaz publica (get_contexto/set_contexto/
get_historial/append_historial) permite sustituir el diccionario en memoria
por Redis u otro backend sin cambiar el contrato usado por Pipeline.

Las sesiones inactivas por mas de SESSION_TTL_SEGUNDOS se purgan de forma
perezosa (no hay hilo de fondo) para evitar crecimiento indefinido de
memoria en un proceso de larga duracion.
"""

import threading
import time

from .config import SESSION_TTL_SEGUNDOS

# Cada cuantas llamadas se intenta una purga oportunista de sesiones vencidas.
_INTERVALO_PURGA = 50


def _nuevo_contexto() -> dict:
    """Estado inicial de contexto para una sesion nueva."""
    return {
        "producto": None,
        "marca": None,
        "talla": None,
        "color": None,
        "modelo": None,
        "material": None,
        "genero": None,
        "cantidad_disponible": None,
        "variantes": None,
        "precio": None,
    }


class SessionStore:
    """
    Store en memoria de estado conversacional por session_id.
    Cada sesion tiene su propio contexto e historial, aislados entre si.
    Thread-safe (Flask puede servir requests concurrentes).
    """

    def __init__(self, ttl_segundos: int = SESSION_TTL_SEGUNDOS):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ttl_segundos = ttl_segundos
        self._contador_llamadas = 0
        # Locks por session_id (H2): permiten serializar el ciclo completo
        # read-process-write de una misma sesion en Pipeline.procesar_mensaje,
        # sin bloquear el procesamiento de sesiones distintas entre si.
        # Independientes de self._lock, que solo protege el diccionario
        # _sessions/_locks en si, no la logica de negocio del Pipeline.
        self._locks: dict[str, threading.Lock] = {}

    def _purgar_expiradas(self) -> None:
        """
        Elimina sesiones sin actividad por mas de self._ttl_segundos.
        Debe llamarse siempre con self._lock ya adquirido (el Lock no es
        reentrante), nunca de forma independiente.
        Tambien purga el lock por sesion asociado (H2), solo si no esta en
        uso en este instante (adquisicion no bloqueante): si el lock esta
        tomado, se deja para la siguiente purga en vez de arriesgar quitarlo
        mientras una sesion "expirada por reloj" todavia esta procesandose.
        """
        ahora = time.time()
        expiradas = [
            sid for sid, s in self._sessions.items()
            if ahora - s["ultimo_acceso"] > self._ttl_segundos
        ]
        for sid in expiradas:
            del self._sessions[sid]
            lock = self._locks.get(sid)
            if lock is not None and lock.acquire(blocking=False):
                lock.release()
                del self._locks[sid]

    def _get_or_create(self, session_id: str) -> dict:
        self._contador_llamadas += 1
        if self._contador_llamadas % _INTERVALO_PURGA == 0:
            self._purgar_expiradas()

        sesion = self._sessions.get(session_id)
        if sesion is None:
            sesion = {
                "contexto": _nuevo_contexto(),
                "historial": [],
                "ultimo_acceso": time.time(),
            }
            self._sessions[session_id] = sesion
        else:
            sesion["ultimo_acceso"] = time.time()
        return sesion

    def get_lock(self, session_id: str) -> threading.Lock:
        """
        Devuelve (creandolo si no existe) el lock asociado a session_id.
        Usar como: `with session_store.get_lock(session_id): ...` para
        serializar el ciclo completo read-process-write de una sesion (H2),
        evitando que dos mensajes casi simultaneos del mismo numero pisen
        la actualizacion de contexto uno del otro. No afecta a otras
        sesiones: cada session_id tiene su propio lock independiente.
        """
        with self._lock:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock

    def get_contexto(self, session_id: str) -> dict:
        """Devuelve una COPIA del contexto. Modificarla no afecta el estado
        interno del store; para persistir cambios hay que llamar a
        set_contexto() explicitamente."""
        with self._lock:
            return dict(self._get_or_create(session_id)["contexto"])

    def set_contexto(self, session_id: str, contexto: dict) -> None:
        with self._lock:
            self._get_or_create(session_id)["contexto"] = contexto

    def get_historial(self, session_id: str) -> list[dict]:
        """Devuelve una COPIA de la lista de historial. Modificarla no
        afecta el estado interno del store; para persistir turnos nuevos
        hay que llamar a append_historial()."""
        with self._lock:
            return list(self._get_or_create(session_id)["historial"])

    def append_historial(self, session_id: str, mensaje_cliente: str, respuesta: str | None) -> None:
        with self._lock:
            sesion = self._get_or_create(session_id)
            sesion["historial"].append({"role": "user", "content": mensaje_cliente})
            if respuesta:
                sesion["historial"].append({"role": "assistant", "content": respuesta})
            if len(sesion["historial"]) > 10:
                sesion["historial"] = sesion["historial"][-10:]


# Instancia global del store (no del estado de cada sesion individual)
session_store = SessionStore()