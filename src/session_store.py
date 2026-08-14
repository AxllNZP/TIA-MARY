"""
Almacen de sesiones en memoria para el pipeline conversacional.
Aisla el contexto (atributos heredados) y el historial de chat por session_id,
evitando que distintos usuarios de WhatsApp compartan estado.

Backend intercambiable: la interfaz publica (get_contexto/set_contexto/
get_historial/append_historial) permite sustituir el diccionario en memoria
por Redis u otro backend sin cambiar el contrato usado por Pipeline.
"""

import threading


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

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, session_id: str) -> dict:
        sesion = self._sessions.get(session_id)
        if sesion is None:
            sesion = {"contexto": _nuevo_contexto(), "historial": []}
            self._sessions[session_id] = sesion
        return sesion

    def get_contexto(self, session_id: str) -> dict:
        with self._lock:
            return self._get_or_create(session_id)["contexto"]

    def set_contexto(self, session_id: str, contexto: dict) -> None:
        with self._lock:
            self._get_or_create(session_id)["contexto"] = contexto

    def get_historial(self, session_id: str) -> list[dict]:
        with self._lock:
            return self._get_or_create(session_id)["historial"]

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