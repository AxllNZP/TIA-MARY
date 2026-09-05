"""
Tests de deduplicacion por message_id para POST /api/webhook-meta (H1 de
la auditoria: Meta puede reintregar el mismo webhook, y sin este mecanismo
el pipeline se ejecutaba y respondia dos veces al mismo mensaje).
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


def _payload_meta(mensaje: str = "Tienen zapatillas Nike?", remitente: str = "51999999999", message_id: str | None = "wamid.TEST123") -> dict:
    msg = {"from": remitente, "text": {"body": mensaje}}
    if message_id is not None:
        msg["id"] = message_id
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [msg]
                }
            }]
        }]
    }


class TestWebhookMetaDedup:
    """Pruebas de deduplicacion por message_id para POST /api/webhook-meta."""

    def test_mismo_message_id_dos_veces_solo_ejecuta_pipeline_una_vez(self, monkeypatch):
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta(message_id="wamid.DUP1")).encode("utf-8")
        firma = _firmar("app_secret_test", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar, \
             patch.object(api_module, "_enviar_mensaje_whatsapp_meta") as mock_enviar:
            mock_procesar.return_value = {
                "respuesta": "Si, tenemos disponibles.",
                "consulta_id": 1,
                "planificacion": {"accion": "consultar_stock"},
            }

            resp1 = client.post(
                "/api/webhook-meta", data=cuerpo, content_type="application/json",
                headers={"X-Hub-Signature-256": firma},
            )
            resp2 = client.post(
                "/api/webhook-meta", data=cuerpo, content_type="application/json",
                headers={"X-Hub-Signature-256": firma},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.get_json()["status"] == "duplicado_ignorado"
        mock_procesar.assert_called_once()
        mock_enviar.assert_called_once()

    def test_message_id_distinto_ejecuta_pipeline_las_dos_veces(self, monkeypatch):
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo1 = json.dumps(_payload_meta(message_id="wamid.A")).encode("utf-8")
        cuerpo2 = json.dumps(_payload_meta(message_id="wamid.B")).encode("utf-8")

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar, \
             patch.object(api_module, "_enviar_mensaje_whatsapp_meta"):
            mock_procesar.return_value = {
                "respuesta": "Si, tenemos disponibles.",
                "consulta_id": 1,
                "planificacion": {"accion": "consultar_stock"},
            }

            client.post("/api/webhook-meta", data=cuerpo1, content_type="application/json",
                         headers={"X-Hub-Signature-256": _firmar("app_secret_test", cuerpo1)})
            client.post("/api/webhook-meta", data=cuerpo2, content_type="application/json",
                         headers={"X-Hub-Signature-256": _firmar("app_secret_test", cuerpo2)})

        assert mock_procesar.call_count == 2

    def test_payload_sin_message_id_no_deduplica_y_procesa(self, monkeypatch):
        """Payload atipico sin 'id': no hay como deduplicar, se procesa igual que antes."""
        api_module = _cargar_app_con_app_secret(monkeypatch, app_secret="app_secret_test")
        client = api_module.app.test_client()

        cuerpo = json.dumps(_payload_meta(message_id=None)).encode("utf-8")
        firma = _firmar("app_secret_test", cuerpo)

        with patch.object(api_module.pipeline, "procesar_mensaje") as mock_procesar, \
             patch.object(api_module, "_enviar_mensaje_whatsapp_meta"):
            mock_procesar.return_value = {
                "respuesta": "Si, tenemos disponibles.",
                "consulta_id": 1,
                "planificacion": {"accion": "consultar_stock"},
            }
            resp1 = client.post("/api/webhook-meta", data=cuerpo, content_type="application/json",
                                 headers={"X-Hub-Signature-256": firma})
            resp2 = client.post("/api/webhook-meta", data=cuerpo, content_type="application/json",
                                 headers={"X-Hub-Signature-256": firma})

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert mock_procesar.call_count == 2