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