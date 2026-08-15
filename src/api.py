"""
API Flask para el asistente de WhatsApp de TÍA MARY.
Provee endpoints para:
- Webhook de WhatsApp
- Dashboard de administración
- Feedback y pautas de mejora
- Chat directo para pruebas
"""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_from_directory

import hashlib
import hmac

from . import database as db
from .config import (
    FLASK_HOST,
    FLASK_PORT,
    FLASK_DEBUG,
    NOMBRE_TIENDA,
    ADMIN_API_TOKEN,
    WEBHOOK_SECRET,
)
from .learning import engine as learning_engine
from .pipeline import pipeline

app = Flask(__name__)


def _autenticacion_admin_valida() -> bool:
    """
    Valida el header 'Authorization: Bearer <token>' contra ADMIN_API_TOKEN.
    Fail-closed: si ADMIN_API_TOKEN no esta configurado, siempre rechaza.
    """
    if not ADMIN_API_TOKEN:
        return False

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False

    token_recibido = auth_header[len("Bearer "):].strip()
    return hmac.compare_digest(token_recibido, ADMIN_API_TOKEN)


def _firma_webhook_valida(cuerpo_crudo: bytes) -> bool:
    """
    Valida la firma HMAC-SHA256 del cuerpo crudo de la solicitud contra
    WEBHOOK_SECRET, esperada en el header 'X-Webhook-Signature' con formato
    'sha256=<hex>'. Fail-closed: si WEBHOOK_SECRET no esta configurado,
    siempre rechaza.
    """
    if not WEBHOOK_SECRET:
        return False

    firma_header = request.headers.get("X-Webhook-Signature", "")
    if not firma_header.startswith("sha256="):
        return False

    firma_recibida = firma_header[len("sha256="):].strip()
    firma_esperada = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), cuerpo_crudo, hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(firma_recibida, firma_esperada)

# ─── ADMIN DASHBOARD HTML ───

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ nombre_tienda }} - Panel de Administración</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a1a; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px 32px; }
        .header h1 { font-size: 24px; margin-bottom: 4px; }
        .header p { opacity: 0.85; font-size: 14px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .stat-card .number { font-size: 32px; font-weight: 700; color: #667eea; }
        .stat-card .label { font-size: 13px; color: #666; margin-top: 4px; }
        .section { background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .section h2 { font-size: 18px; margin-bottom: 16px; color: #333; border-bottom: 2px solid #667eea; padding-bottom: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
        th { background: #f9fafb; font-weight: 600; color: #555; }
        tr:hover { background: #f5f7ff; }
        .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .badge-positiva { background: #d4edda; color: #155724; }
        .badge-negativa { background: #f8d7da; color: #721c24; }
        .badge-neutral { background: #e2e3e5; color: #383d41; }
        form { display: flex; flex-direction: column; gap: 12px; }
        input, textarea, select { padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; font-family: inherit; }
        textarea { min-height: 80px; resize: vertical; }
        button { padding: 10px 24px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
        button:hover { background: #5a6fd6; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .flex-row { display: flex; gap: 12px; align-items: center; }
        .msg-box { background: #f9fafb; border-left: 3px solid #667eea; padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 8px 0; font-size: 13px; }
        .refresh { margin-bottom: 12px; }
        .feedback-form { display: flex; gap: 8px; align-items: center; }
        .feedback-form select { padding: 4px 8px; font-size: 12px; }
        .feedback-form button { padding: 4px 12px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏪 {{ nombre_tienda }} - Panel de Administración</h1>
        <p>Zona de mejora continua del asistente de WhatsApp</p>
    </div>
    <div class="container">
        <!-- Estadísticas -->
        <div class="stats" id="stats">
            {% for s in stats %}
            <div class="stat-card">
                <div class="number">{{ s.valor }}</div>
                <div class="label">{{ s.label }}</div>
            </div>
            {% endfor %}
        </div>

        <!-- Pautas de mejora -->
        <div class="section">
            <h2>📝 Pautas de Mejora Activas</h2>
            <form id="pauta-form" onsubmit="guardarPauta(event)">
                <div class="flex-row">
                    <select name="tipo" required>
                        <option value="planner">Planner (clasificación)</option>
                        <option value="responder">Responder (respuestas)</option>
                        <option value="general">General</option>
                    </select>
                    <input type="text" name="contenido" placeholder="Ej: Cuando pregunten por 'chompas', trátalo como 'casaca'..." style="flex:1;" required>
                    <button type="submit">➕ Agregar Pauta</button>
                </div>
            </form>
            <div id="pautas-lista" style="margin-top:12px;">
                {% for p in pautas %}
                <div class="msg-box">
                    <strong>[{{ p.tipo }}]</strong> {{ p.contenido }}
                    <small style="color:#999;margin-left:8px;">{{ p.creado_en }}</small>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- Historial de consultas -->
        <div class="section">
            <h2>📋 Historial de Consultas</h2>
            <button class="refresh" onclick="location.reload()">🔄 Refrescar</button>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Fecha</th>
                        <th>Cliente</th>
                        <th>Respuesta</th>
                        <th>Producto</th>
                        <th>Encontrado</th>
                        <th>Feedback</th>
                        <th>Acción</th>
                    </tr>
                </thead>
                <tbody>
                    {% for c in consultas %}
                    <tr>
                        <td>{{ c.id }}</td>
                        <td style="white-space:nowrap;">{{ c.timestamp[:16] }}</td>
                        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;" title="{{ c.mensaje_cliente }}">{{ c.mensaje_cliente[:60] }}{% if c.mensaje_cliente|length > 60 %}...{% endif %}</td>
                        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;" title="{{ c.respuesta_enviada or '' }}">{{ (c.respuesta_enviada or '')[:60] }}{% if (c.respuesta_enviada or '')|length > 60 %}...{% endif %}</td>
                        <td>{{ c.producto_buscado or '-' }}</td>
                        <td>{{ '✅' if c.encontrado else '❌' }}</td>
                        <td>
                            {% if c.feedback_calificacion %}
                            <span class="badge badge-{{ c.feedback_calificacion }}">{{ c.feedback_calificacion }}</span>
                            {% else %}
                            <span class="badge badge-neutral">sin feedback</span>
                            {% endif %}
                        </td>
                        <td>
                            <form class="feedback-form" onsubmit="guardarFeedback(event, {{ c.id }})">
                                <select name="calificacion" required>
                                    <option value="">--</option>
                                    <option value="positiva">👍</option>
                                    <option value="negativa">👎</option>
                                </select>
                                <button type="submit">OK</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <!-- Chat de prueba -->
        <div class="section">
            <h2>💬 Chat de Prueba</h2>
            <form id="chat-form" onsubmit="enviarChat(event)">
                <div class="flex-row">
                    <input type="text" id="chat-input" placeholder="Escribe un mensaje como si fueras un cliente..." style="flex:1;" required>
                    <button type="submit">Enviar</button>
                </div>
            </form>
            <div id="chat-response" style="margin-top:12px;"></div>
        </div>
    </div>

    <script>
        async function guardarPauta(event) {
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);
            const data = {
                tipo: formData.get('tipo'),
                contenido: formData.get('contenido')
            };
            const resp = await fetch('/api/pautas', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (resp.ok) {
                location.reload();
            } else {
                alert('Error al guardar pauta');
            }
        }

        async function guardarFeedback(event, consultaId) {
            event.preventDefault();
            const form = event.target;
            const formData = new FormData(form);
            const data = {
                consulta_id: consultaId,
                calificacion: formData.get('calificacion')
            };
            const resp = await fetch('/api/feedback', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            if (resp.ok) {
                location.reload();
            } else {
                alert('Error al guardar feedback');
            }
        }

        async function enviarChat(event) {
            event.preventDefault();
            const input = document.getElementById('chat-input');
            const responseDiv = document.getElementById('chat-response');
            const mensaje = input.value;

            responseDiv.innerHTML = '<p style="color:#666;">⏳ Procesando...</p>';

            const resp = await fetch('/api/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mensaje: mensaje})
            });

            const result = await resp.json();
            responseDiv.innerHTML = `
                <div class="msg-box"><strong>🧑 Cliente:</strong> ${mensaje}</div>
                <div class="msg-box"><strong>🤖 ${result.nombre_tienda}:</strong> ${result.respuesta}</div>
                <details style="margin-top:8px;font-size:12px;color:#666;">
                    <summary>🔍 Ver detalles (planificación + inventario)</summary>
                    <pre>${JSON.stringify(result.detalles, null, 2)}</pre>
                </details>
            `;
            input.value = '';
        }
    </script>
</body>
</html>"""


# ─── RUTAS ───

@app.route("/")
def index():
    """Redirecciona al panel de administración."""
    return '<meta http-equiv="refresh" content="0;url=/admin">'


@app.route("/admin")
def admin():
    """Panel de administración."""
    stats_data = learning_engine.get_estadisticas()
    consultas_data = learning_engine.get_historial(limit=30)
    pautas_data = db.get_pautas_activas()

    stats_display = [
        {"label": "Consultas Totales", "valor": stats_data["total_consultas"]},
        {"label": "Productos en BD", "valor": stats_data["total_productos"]},
        {"label": "Con Stock", "valor": stats_data["productos_con_stock"]},
        {"label": "👍 Feedback Positivo", "valor": stats_data["feedback_positivo"]},
        {"label": "👎 Feedback Negativo", "valor": stats_data["feedback_negativo"]},
        {"label": "Pautas Activas", "valor": stats_data["pautas_activas"]},
    ]

    return render_template_string(
        ADMIN_HTML,
        nombre_tienda=NOMBRE_TIENDA,
        stats=stats_display,
        consultas=consultas_data,
        pautas=[dict(p) for p in pautas_data],
    )


# ─── API ENDPOINTS ───

@app.route("/api/webhook", methods=["POST"])
def webhook():
    """
    Endpoint para recibir mensajes de WhatsApp (simula Twilio/Meta webhook).
    Requiere firma valida en el header 'X-Webhook-Signature: sha256=<hmac>'
    calculada sobre el cuerpo crudo con WEBHOOK_SECRET.
    Espera JSON: {"mensaje": "texto del cliente", "session_id": "numero_whatsapp" (opcional)}
    session_id debe ser el identificador estable del remitente de WhatsApp
    (ej. numero de telefono/wa_id) cuando se integre el proveedor real.
    Si no se envia, se usa "default" (retrocompatible con el simulador actual).
    """
    if not _firma_webhook_valida(request.get_data()):
        return jsonify({"error": "Firma invalida o ausente"}), 401

    data = request.get_json(force=True, silent=True)
    if not data or "mensaje" not in data:
        return jsonify({"error": "Se requiere el campo 'mensaje'"}), 400

    mensaje = data["mensaje"].strip()
    if not mensaje:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    session_id = data.get("session_id") or "default"
    resultado = pipeline.procesar_mensaje(mensaje, session_id=session_id)

    return jsonify(
        {
            "respuesta": resultado["respuesta"],
            "consulta_id": resultado["consulta_id"],
            "accion": resultado["planificacion"]["accion"]
            if resultado["planificacion"]
            else "error",
        }
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Endpoint para pruebas directas (sin WhatsApp).
    Espera JSON: {"mensaje": "texto del cliente", "session_id": "..." (opcional)}
    Retorna la respuesta + detalles internos.
    """
    data = request.get_json(force=True, silent=True)
    if not data or "mensaje" not in data:
        return jsonify({"error": "Se requiere el campo 'mensaje'"}), 400

    mensaje = data["mensaje"].strip()
    if not mensaje:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    session_id = data.get("session_id") or "default"
    resultado = pipeline.procesar_mensaje(mensaje, session_id=session_id)

    return jsonify(
        {
            "respuesta": resultado["respuesta"],
            "consulta_id": resultado["consulta_id"],
            "nombre_tienda": NOMBRE_TIENDA,
            "detalles": {
                "planificacion": resultado["planificacion"],
                "inventario": {
                    k: v
                    for k, v in (resultado.get("inventario") or {}).items()
                    if not k.startswith("_")
                },
                "error": resultado.get("error"),
            },
        }
    )


@app.route("/api/feedback", methods=["POST"])
def feedback():
    """Registra feedback sobre una consulta."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    consulta_id = data.get("consulta_id")
    calificacion = data.get("calificacion")
    comentario = data.get("comentario")

    if not consulta_id or not calificacion:
        return jsonify({"error": "Se requiere consulta_id y calificacion"}), 400

    if calificacion not in ("positiva", "negativa", "neutral"):
        return jsonify({"error": "calificacion debe ser positiva, negativa o neutral"}), 400

    learning_engine.add_feedback(consulta_id, calificacion, comentario)

    return jsonify({"ok": True, "mensaje": "Feedback registrado"})


@app.route("/api/pautas", methods=["GET", "POST"])
def pautas():
    """GET: lista pautas activas. POST: crea nueva pauta (requiere admin)."""
    if request.method == "GET":
        tipo = request.args.get("tipo")
        pautas_list = db.get_pautas_activas(tipo=tipo if tipo else None)
        return jsonify([dict(p) for p in pautas_list])

    # POST — requiere autenticacion de administrador antes de persistir nada
    if not _autenticacion_admin_valida():
        return jsonify({"error": "No autorizado"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    tipo = data.get("tipo", "general")
    contenido = data.get("contenido", "").strip()

    if not contenido:
        return jsonify({"error": "Se requiere 'contenido'"}), 400

    pauta_id = learning_engine.add_pauta(tipo, contenido)
    return jsonify({"ok": True, "id": pauta_id, "mensaje": "Pauta creada"})


@app.route("/api/stats", methods=["GET"])
def stats():
    """Retorna estadísticas del sistema."""
    return jsonify(learning_engine.get_estadisticas())


@app.route("/api/contexto-mejora", methods=["GET"])
def contexto_mejora():
    """Retorna contexto completo para mejora (consultas negativas, pautas, etc.)."""
    return jsonify(learning_engine.get_contexto_mejora())


def run_server():
    """Inicia el servidor Flask."""
    print(f"\n{'='*60}")
    print(f"  🏪 {NOMBRE_TIENDA} - Asistente de WhatsApp")
    print(f"  Servidor iniciado en http://localhost:{FLASK_PORT}")
    print(f"  Panel de administración: http://localhost:{FLASK_PORT}/admin")
    print(f"{'='*60}\n")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


if __name__ == "__main__":
    # Inicializar BD antes de arrancar
    db.init_db()
    insertados = db.seed_from_json()
    if insertados:
        print(f"✅ {insertados} productos cargados desde seed_productos.json")

    run_server()