"""
Tests de autenticacion para POST /api/pautas (A2).
Verifican que solo un administrador con token valido puede persistir pautas,
y que la verificacion ocurre antes de escribir en la base de datos.
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def _cargar_app_con_token(monkeypatch, token: str | None):
    """
    Recarga src.config y src.api con ADMIN_API_TOKEN controlado,
    ya que api.py lee el token al momento de importarse.
    """
    if token is None:
        monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_API_TOKEN", token)

    for mod in ("src.config", "src.api"):
        if mod in sys.modules:
            del sys.modules[mod]

    api_module = importlib.import_module("src.api")
    return api_module


class TestPautasAuth:
    """Pruebas de autenticacion para POST /api/pautas."""

    def test_sin_token_configurado_rechaza(self, monkeypatch):
        """Si ADMIN_API_TOKEN no esta configurado, debe rechazar (fail-closed)."""
        api_module = _cargar_app_con_token(monkeypatch, token=None)
        client = api_module.app.test_client()

        resp = client.post("/api/pautas", json={"tipo": "general", "contenido": "test"})
        assert resp.status_code == 401

    def test_sin_header_authorization_rechaza(self, monkeypatch):
        """Solicitud sin header Authorization debe ser rechazada."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.post("/api/pautas", json={"tipo": "general", "contenido": "test"})
        assert resp.status_code == 401

    def test_token_invalido_rechaza(self, monkeypatch):
        """Un token incorrecto debe ser rechazado."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.post(
            "/api/pautas",
            json={"tipo": "general", "contenido": "test"},
            headers={"Authorization": "Bearer token_incorrecto"},
        )
        assert resp.status_code == 401

    def test_token_valido_permite_persistir(self, monkeypatch):
        """Un token correcto debe permitir crear la pauta."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.post(
            "/api/pautas",
            json={"tipo": "general", "contenido": "TEST A2: pauta autorizada"},
            headers={"Authorization": "Bearer secreto123"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "id" in data

        # Limpieza: eliminar la pauta creada para no ensuciar la BD de pruebas
        from src import database as db
        import sqlite3
        conn = sqlite3.connect(str(db.DATABASE_PATH))
        conn.execute("DELETE FROM pautas WHERE id = ?", (data["id"],))
        conn.commit()
        conn.close()

    def test_no_persiste_sin_autenticacion(self, monkeypatch):
        """
        Verifica que un intento sin autenticacion NO deja rastro en la BD:
        el conteo de pautas antes y despues del intento rechazado debe ser igual.
        """
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        from src import database as db

        conteo_antes = db.get_estadisticas()["pautas_activas"]

        resp = client.post(
            "/api/pautas",
            json={"tipo": "general", "contenido": "TEST A2: no deberia persistir"},
        )
        assert resp.status_code == 401

        conteo_despues = db.get_estadisticas()["pautas_activas"]
        assert conteo_antes == conteo_despues

    def test_get_pautas_sin_token_rechaza(self, monkeypatch):
        """
        GET /api/pautas ahora requiere autenticacion de administrador (pendiente
        resuelto tras A2): las pautas revelan reglas de negocio/prompt-tuning
        activas, util para disenar ataques de prompt injection dirigidos.
        """
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.get("/api/pautas")
        assert resp.status_code == 401

    def test_get_pautas_con_token_invalido_rechaza(self, monkeypatch):
        """GET /api/pautas con token incorrecto debe rechazar."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.get(
            "/api/pautas",
            headers={"Authorization": "Bearer token_incorrecto"},
        )
        assert resp.status_code == 401

    def test_get_pautas_con_token_valido_permite_lectura(self, monkeypatch):
        """GET /api/pautas con token correcto debe retornar la lista de pautas."""
        api_module = _cargar_app_con_token(monkeypatch, token="secreto123")
        client = api_module.app.test_client()

        resp = client.get(
            "/api/pautas",
            headers={"Authorization": "Bearer secreto123"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_pautas_sin_token_configurado_rechaza(self, monkeypatch):
        """Si ADMIN_API_TOKEN no esta configurado, GET tambien debe rechazar (fail-closed)."""
        api_module = _cargar_app_con_token(monkeypatch, token=None)
        client = api_module.app.test_client()

        resp = client.get("/api/pautas")
        assert resp.status_code == 401