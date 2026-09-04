"""
Tests de autenticacion para POST /api/feedback.
Mismo patron que test_pautas_auth.py, reutilizando _autenticacion_admin_valida.
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _cargar_app_con_token(monkeypatch, token: str | None):
    if token is None:
        monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_TOKEN", token)

    for mod in ("src.config", "src.api"):
        if mod in sys.modules:
            del sys.modules[mod]

    return importlib.import_module("src.api")


class TestFeedbackAuth:
    """Pruebas de autenticacion para POST /api/feedback."""

    def test_sin_token_configurado_rechaza(self, monkeypatch):
        api_module = _cargar_app_con_token(monkeypatch, token=None)
        client = api_module.app.test_client()

        resp = client.post("/api/feedback", json={"consulta_id": 1, "calificacion": "positiva"})
        assert resp.status_code == 401

    def test_sin_header_authorization_rechaza(self, monkeypatch):
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.post("/api/feedback", json={"consulta_id": 1, "calificacion": "positiva"})
        assert resp.status_code == 401

    def test_token_invalido_rechaza(self, monkeypatch):
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.post(
            "/api/feedback",
            json={"consulta_id": 1, "calificacion": "positiva"},
            headers={"Authorization": "Bearer token_incorrecto"},
        )
        assert resp.status_code == 401

    def test_token_valido_permite_guardar_feedback(self, monkeypatch):
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        from src import database as db
        consulta_id = db.registrar_consulta(
            mensaje_cliente="test", accion="consultar_stock",
            encontrado=True, respuesta_enviada="respuesta de prueba",
        )

        resp = client.post(
            "/api/feedback",
            json={"consulta_id": consulta_id, "calificacion": "positiva"},
            headers={"Authorization": "Bearer secreto123"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

        # Limpieza
        import sqlite3
        conn = sqlite3.connect(str(db.DATABASE_PATH))
        conn.execute("DELETE FROM feedback WHERE consulta_id = ?", (consulta_id,))
        conn.execute("DELETE FROM consultas WHERE id = ?", (consulta_id,))
        conn.commit()
        conn.close()

    def test_no_persiste_sin_autenticacion(self, monkeypatch):
        """Un intento sin autenticacion no debe dejar rastro en la BD."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        from src import database as db
        consulta_id = db.registrar_consulta(
            mensaje_cliente="test", accion="consultar_stock",
            encontrado=True, respuesta_enviada="respuesta de prueba",
        )

        resp = client.post(
            "/api/feedback",
            json={"consulta_id": consulta_id, "calificacion": "positiva"},
        )
        assert resp.status_code == 401

        historial = db.get_ultimas_consultas(limit=1)
        assert historial[0]["feedback_calificacion"] is None

        import sqlite3
        conn = sqlite3.connect(str(db.DATABASE_PATH))
        conn.execute("DELETE FROM consultas WHERE id = ?", (consulta_id,))
        conn.commit()
        conn.close()