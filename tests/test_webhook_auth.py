"""
Tests de autenticacion por firma HMAC para POST /api/webhook (A1).
Verifican que solo solicitudes con firma valida llegan al pipeline,
y que las rechazadas no ejecutan procesar_mensaje().
"""

import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _cargar_app_con_secret(monkeypatch, secret: str | None):
    """
    Recarga src.config y src.api con WEBHOOK_SECRET controlado,
    ya que api.py lee el secreto al momento de importarse.
    """
    if secret is None:
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    else:
        monkeypatch.setenv("WEBHOOK_SECRET", secret)

    for mod in ("src.config", "src.api"):
        if mod in sys.modules:
            del sys.modules[mod]

    return importlib.import_module("src.api")


def _firmar(secret: str, cuerpo: bytes) -> str:
    """Genera el header de firma esperado por el webhook."""
    firma = hmac.new(secret.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return f"sha256={firma}"


class TestWebhookAuth:
    """Pruebas de autenticacion por firma para POST /api/webhook."""

    def test_firma_valida_acepta_y_ejecuta_pipeline(self, monkeypatch):
        """Firma correcta: debe aceptar y llamar al pipeline."""
        api_module = _cargar_app_con_secret(monkeypatch, secret="secreto_webhook")
        client = api_module.app.test_client()

        payload = {"mensaje": "Tienen zapatillas Nike?"}
        cuerpo = json.dumps(payload).encode("utf-8")
        firma = _firmar("secreto_webhook", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            mock_procesar.return_value = {
                "respuesta": "Si, tenemos disponibles.",
                "consulta_id": 1,
                "planificacion": {"accion": "consultar_stock"},
            }
            resp = client.post(
                "/api/webhook",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Webhook-Signature": firma},
            )

        assert resp.status_code == 200
        mock_procesar.assert_called_once()

    def test_sin_firma_rechaza_y_no_ejecuta_pipeline(self, monkeypatch):
        """Sin header de firma: debe rechazar y NO llamar al pipeline."""
        api_module = _cargar_app_con_secret(monkeypatch, secret="secreto_webhook")
        client = api_module.app.test_client()

        payload = {"mensaje": "Tienen zapatillas Nike?"}
        cuerpo = json.dumps(payload).encode("utf-8")

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post("/api/webhook", data=cuerpo, content_type="application/json")

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_firma_invalida_rechaza_y_no_ejecuta_pipeline(self, monkeypatch):
        """Firma incorrecta: debe rechazar y NO llamar al pipeline."""
        api_module = _cargar_app_con_secret(monkeypatch, secret="secreto_webhook")
        client = api_module.app.test_client()

        payload = {"mensaje": "Tienen zapatillas Nike?"}
        cuerpo = json.dumps(payload).encode("utf-8")
        firma_incorrecta = "sha256=" + "0" * 64

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Webhook-Signature": firma_incorrecta},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_sin_webhook_secret_configurado_rechaza(self, monkeypatch):
        """Si WEBHOOK_SECRET no esta configurado, debe rechazar (fail-closed)."""
        api_module = _cargar_app_con_secret(monkeypatch, secret=None)
        client = api_module.app.test_client()

        payload = {"mensaje": "Tienen zapatillas Nike?"}
        cuerpo = json.dumps(payload).encode("utf-8")
        firma = _firmar("cualquier_cosa", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook",
                data=cuerpo,
                content_type="application/json",
                headers={"X-Webhook-Signature": firma},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()

    def test_firma_valida_pero_cuerpo_modificado_rechaza(self, monkeypatch):
        """
        Firma calculada sobre un cuerpo distinto al enviado debe rechazar
        (protege contra manipulacion del payload tras firmar).
        """
        api_module = _cargar_app_con_secret(monkeypatch, secret="secreto_webhook")
        client = api_module.app.test_client()

        cuerpo_original = json.dumps({"mensaje": "Tienen zapatillas Nike?"}).encode("utf-8")
        firma_del_original = _firmar("secreto_webhook", cuerpo_original)

        cuerpo_modificado = json.dumps({"mensaje": "Venden laptops gratis?"}).encode("utf-8")

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar:
            resp = client.post(
                "/api/webhook",
                data=cuerpo_modificado,
                content_type="application/json",
                headers={"X-Webhook-Signature": firma_del_original},
            )

        assert resp.status_code == 401
        mock_procesar.assert_not_called()