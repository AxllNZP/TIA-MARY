"""
Tests de aislamiento de sesion (C1).
Verifican que distintos session_id no comparten contexto ni historial,
y que una sesion nueva no hereda estado de otra. No requieren Ollama.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_store import SessionStore


class TestSessionIsolation:
    """Pruebas de aislamiento entre sesiones distintas."""

    def test_contextos_independientes_por_defecto(self):
        """Dos sesiones nuevas deben partir con contexto vacio e independiente."""
        store = SessionStore()
        ctx_a = store.get_contexto("usuario_A")
        ctx_b = store.get_contexto("usuario_B")
        assert ctx_a == ctx_b  # ambos vacios al inicio
        assert ctx_a is not ctx_b  # pero son objetos distintos, no compartidos

    def test_set_contexto_no_contamina_otra_sesion(self):
        """Actualizar el contexto de A no debe afectar el contexto de B."""
        store = SessionStore()

        store.set_contexto("usuario_A", {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": None, "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        })
        store.set_contexto("usuario_B", {
            "producto": "polo", "marca": "Lacoste", "talla": "M",
            "color": "azul", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 2, "variantes": None, "precio": 120.0,
        })

        ctx_a = store.get_contexto("usuario_A")
        ctx_b = store.get_contexto("usuario_B")

        assert ctx_a["producto"] == "zapatillas"
        assert ctx_b["producto"] == "polo"
        assert ctx_a != ctx_b  # estado(A) != estado(B)

    def test_historial_independiente_por_sesion(self):
        """El historial de chat de A no debe mezclarse con el de B."""
        store = SessionStore()

        store.append_historial("usuario_A", "Tienen zapatillas Nike talla 42?", "Si, 3 unidades.")
        store.append_historial("usuario_B", "Tienen polos azules?", "Si, Lacoste y Tommy.")

        hist_a = store.get_historial("usuario_A")
        hist_b = store.get_historial("usuario_B")

        assert hist_a[0]["content"] == "Tienen zapatillas Nike talla 42?"
        assert hist_b[0]["content"] == "Tienen polos azules?"
        assert hist_a != hist_b

    def test_conversacion_continua_no_cruza_sesiones(self):
        """
        Simula: A continua su conversacion (2do turno) mientras B tambien
        continua la suya. Cada uno debe ver solo su propio historial.
        """
        store = SessionStore()

        # Turno 1
        store.append_historial("usuario_A", "Tienen zapatillas Nike talla 42?", "Si, 3 unidades.")
        store.append_historial("usuario_B", "Tienen polos azules?", "Si, Lacoste y Tommy.")

        # Turno 2 (seguimiento de cada uno)
        store.append_historial("usuario_A", "cuanto cuesta?", "S/ 250.00.")
        store.append_historial("usuario_B", "el Lacoste en talla L?", "Si, tenemos 2 unidades.")

        hist_a = store.get_historial("usuario_A")
        hist_b = store.get_historial("usuario_B")

        assert len(hist_a) == 4
        assert len(hist_b) == 4
        assert "zapatillas" in hist_a[0]["content"]
        assert "polos" in hist_b[0]["content"]
        # Ningun mensaje de B debe aparecer en el historial de A
        contenidos_a = [m["content"] for m in hist_a]
        assert "el Lacoste en talla L?" not in contenidos_a

    def test_sesion_nueva_no_hereda_contexto(self):
        """Una sesion nueva (session_id nunca antes usado) debe partir en blanco."""
        store = SessionStore()
        store.set_contexto("usuario_A", {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": None, "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        })

        ctx_nueva = store.get_contexto("usuario_C")  # sesion nunca usada
        assert ctx_nueva["producto"] is None
        assert ctx_nueva["marca"] is None

class TestOrdenHistorialM3:
    """
    Pruebas de M3: el historial que 'recibiria' el Responder en un turno
    dado debe contener solo los turnos ANTERIORES (sin el mensaje actual
    duplicado), y tras persistir el turno actual, el historial acumulado
    no debe perder, duplicar ni desordenar ningun mensaje.
    Simula el flujo real de pipeline.procesar_mensaje() usando
    session_store directamente, sin requerir Ollama.
    """

    def test_historial_en_turno_2_no_incluye_mensaje_actual_duplicado(self):
        """
        Al procesar el turno 2, el historial leido ANTES de generar la
        respuesta (lo que recibiria el Responder) debe tener exactamente
        el turno 1 (2 mensajes), sin el mensaje del turno 2 todavia.
        """
        store = SessionStore()
        session_id = "usuario_test"

        # Turno 1 completo (simulando el fin de procesar_mensaje)
        store.append_historial(session_id, "Tienen zapatillas Nike talla 42?", "Si, 3 unidades.")

        # Turno 2: lo que el pipeline leeria ANTES de llamar al Responder
        historial_para_responder = store.get_historial(session_id)

        assert len(historial_para_responder) == 2  # solo el turno 1 (user+assistant)
        assert historial_para_responder[0]["content"] == "Tienen zapatillas Nike talla 42?"
        assert historial_para_responder[1]["content"] == "Si, 3 unidades."
        # El mensaje del turno 2 ("cuanto cuesta?") NO debe estar aqui todavia
        contenidos = [m["content"] for m in historial_para_responder]
        assert "cuanto cuesta?" not in contenidos

    def test_historial_acumulado_sin_duplicados_tras_dos_turnos(self):
        """Tras completar 2 turnos, el historial debe tener 4 mensajes, sin duplicados."""
        store = SessionStore()
        session_id = "usuario_test"

        store.append_historial(session_id, "Tienen zapatillas Nike talla 42?", "Si, 3 unidades.")
        store.append_historial(session_id, "cuanto cuesta?", "S/ 250.00.")

        historial_final = store.get_historial(session_id)

        assert len(historial_final) == 4
        contenidos = [m["content"] for m in historial_final]
        assert contenidos == [
            "Tienen zapatillas Nike talla 42?",
            "Si, 3 unidades.",
            "cuanto cuesta?",
            "S/ 250.00.",
        ]
        assert len(contenidos) == len(set(contenidos))  # sin duplicados

    def test_orden_cronologico_se_preserva(self):
        """Los mensajes deben quedar en el orden exacto en que ocurrieron."""
        store = SessionStore()
        session_id = "usuario_test"

        store.append_historial(session_id, "primero", "respuesta uno")
        store.append_historial(session_id, "segundo", "respuesta dos")
        store.append_historial(session_id, "tercero", "respuesta tres")

        historial = store.get_historial(session_id)
        roles = [m["role"] for m in historial]
        contenidos = [m["content"] for m in historial]

        assert roles == ["user", "assistant"] * 3
        assert contenidos == [
            "primero", "respuesta uno",
            "segundo", "respuesta dos",
            "tercero", "respuesta tres",
        ]