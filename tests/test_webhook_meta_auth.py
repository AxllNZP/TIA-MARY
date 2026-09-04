"""
Tests de autenticacion por firma HMAC (X-Hub-Signature-256) para
POST /api/webhook-meta. Mismo patron que test_webhook_auth.py, adaptado
al secreto y header propios de Meta.
"""

import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _cargar_app_con_app_secret(monkeypatch, app_secret: str | None):
    """
    Recarga src.config y src.api con WHATSAPP_APP_SECRET controlado,
    ya que api.py lo lee al momento de importarse.
    """
    if app_secret is None:
        monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    else:
        monkeypatch.setenv("WHATSAPP_APP_SECRET", app_secret)

    for mod in ("src.config", "src.api"):
        if mod in sys.modules:
            del sys.modules[mod]

    return importlib.import_module("src.api")


def _firmar(secret: str, cuerpo: bytes) -> str:
    firma = hmac.new(secret.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return f"sha256={firma}"


def _payload_meta(mensaje: str = "Tienen zapatillas Nike?", remitente: str = "51999999999") -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{"from": remitente, "text": {"body": mensaje}}]
                }
            }]
        }]
    }


class TestWebhookMetaAuth:
    """Pruebas de autenticacion por firma para POST /api/webhook-meta."""

    def test_firma_valida_acepta_y_ejecuta_pipeline(self, monkeypatch):
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta()).encode("utf-8")
        firma = _firmar("app_secret_test", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar, \
             patch.object(api_module, "_enviar_mensaje_whatsapp_meta") as mock_enviar:
            mock_procesar.return_value = {
                "respuesta": "Si, tenemos disponibles.",
                "consulta_id": 1,
                "planificacion": {"accion": "consultar_stock"},
            }
            resp = client.post(
                "/api/webhook-meta",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Hub-Signature-256": firma},
            )

        assert resp.status_code == 200
        mock_procesar.assert_called_once()

    def test_sin_firma_rechaza_y_no_ejecuta_pipeline(self, monkeypatch):
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta()).encode("utf-8")

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post("/api/webhook-meta", data=cuerpo, content_type="application/json")

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_firma_invalida_rechaza_y_no_ejecuta_pipeline(self, monkeypatch):
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta()).encode("utf-8")
        firma_incorrecta = "sha256=" + "0" * 64

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook-meta",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Hub-Signature-256": firma_incorrecta},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_sin_app_secret_configurado_rechaza(self, monkeypatch):
        """Fail-closed: sin WHATSAPP_APP_SECRET, debe rechazar siempre."""
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret=None)
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta()).encode("utf-8")
        firma = _firmar("cualquier_cosa", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook-meta",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Hub-Signature-256": firma},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_firma_valida_pero_cuerpo_modificado_rechaza(self, monkeypatch):
        """Protege contra manipulacion del payload despues de firmarlo."""
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo_original = json.dumps(_payload_meta(mensaje="Tienen zapatillas Nike?")).encode("utf-8")
        firma_del_original = _firmar("app_secret_test", cuerpo_original)

        cuerpo_modificado = json.dumps(_payload_meta(mensaje="Venden laptops gratis?")).encode("utf-8")

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook-meta",
                data=cuerpo_modificado,
                content_type="application/json",
                headers={"X-Hub-Signature-256": firma_del_original},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_verify_get_con_token_correcto_responde_challenge(self, monkeypatch):
        """GET de verificacion inicial de Meta: token correcto -> devuelve el challenge."""
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify_test")
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        resp = client.get(
            "/api/webhook-meta",
            query_string={"hub.mode": "subscribe", "hub.verify_token": "verify_test", "hub.challenge": "12345"},
        )
        assert resp.status_code == 200
        assert resp.data.decode() == "12345"

    def test_verify_get_con_token_incorrecto_rechaza(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "verify_test")
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        resp = client.get(
            "/api/webhook-meta",
            query_string={"hub.mode": "subscribe", "hub.verify_token": "token_incorrecto", "hub.challenge": "12345"},
        )
        assert resp.status_code == 403