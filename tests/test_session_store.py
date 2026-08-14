"""
Tests de aislamiento de sesiones (C1).
Verifican que SessionStore mantiene contexto e historial independientes
por session_id, y que Pipeline opera sobre ese estado via session_store
en vez de estado global compartido.
No requieren Ollama: no invocan Planner ni Responder.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_store import SessionStore
from src.pipeline import Pipeline


class TestSessionStoreAislamiento:
    """Pruebas unitarias del SessionStore (sin LLM)."""

    def test_contextos_aislados_entre_sesiones(self):
        """Dos sesiones distintas deben tener contextos independientes."""
        store = SessionStore()

        contexto_a = store.get_contexto("usuario_A")
        contexto_a["producto"] = "zapatillas"
        contexto_a["marca"] = "Nike"
        store.set_contexto("usuario_A", contexto_a)

        contexto_b = store.get_contexto("usuario_B")
        contexto_b["producto"] = "polo"
        contexto_b["marca"] = "Lacoste"
        store.set_contexto("usuario_B", contexto_b)

        final_a = store.get_contexto("usuario_A")
        final_b = store.get_contexto("usuario_B")

        assert final_a["producto"] == "zapatillas"
        assert final_a["marca"] == "Nike"
        assert final_b["producto"] == "polo"
        assert final_b["marca"] == "Lacoste"
        assert final_a != final_b

    def test_historial_aislado_entre_sesiones(self):
        """El historial de chat de una sesion no debe mezclarse con el de otra."""
        store = SessionStore()

        store.append_historial("usuario_A", "Tienen zapatillas Nike?", "Si, tenemos 3 unidades.")
        store.append_historial("usuario_B", "Tienen polos azules?", "Si, tenemos Lacoste y Tommy.")

        historial_a = store.get_historial("usuario_A")
        historial_b = store.get_historial("usuario_B")

        assert len(historial_a) == 2
        assert len(historial_b) == 2
        assert historial_a[0]["content"] == "Tienen zapatillas Nike?"
        assert historial_b[0]["content"] == "Tienen polos azules?"
        assert historial_a != historial_b

    def test_sesion_nueva_no_hereda_historial_de_otra(self):
        """Una sesion recien creada debe iniciar sin historial ni contexto previos."""
        store = SessionStore()

        store.append_historial("usuario_A", "Tienen zapatillas Nike?", "Si, 3 unidades.")
        contexto_a = store.get_contexto("usuario_A")
        contexto_a["producto"] = "zapatillas"
        store.set_contexto("usuario_A", contexto_a)

        # Sesion nueva, nunca antes vista
        historial_c = store.get_historial("usuario_C")
        contexto_c = store.get_contexto("usuario_C")

        assert historial_c == []
        assert contexto_c["producto"] is None

    def test_continuidad_dentro_de_la_misma_sesion(self):
        """Una misma sesion SI debe conservar su contexto entre llamadas sucesivas."""
        store = SessionStore()

        contexto = store.get_contexto("usuario_A")
        contexto["producto"] = "zapatillas"
        contexto["marca"] = "Nike"
        store.set_contexto("usuario_A", contexto)

        contexto_recuperado = store.get_contexto("usuario_A")
        assert contexto_recuperado["producto"] == "zapatillas"
        assert contexto_recuperado["marca"] == "Nike"


class TestPipelineUsaSessionStore:
    """
    Verifica que Pipeline ya no mantiene estado propio (_contexto_sesion /
    _historial_chat) y que opera sobre session_store por session_id.
    """

    def test_pipeline_no_tiene_estado_de_instancia_de_sesion(self):
        """Pipeline no debe exponer _contexto_sesion ni _historial_chat como atributos."""
        p = Pipeline()
        assert not hasattr(p, "_contexto_sesion")
        assert not hasattr(p, "_historial_chat")

    def test_merge_atributos_usa_contexto_por_parametro(self):
        """_merge_atributos debe fusionar el plan con el contexto pasado explicitamente,
        sin leer estado propio de la instancia."""
        p = Pipeline()

        contexto_a = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": None, "modelo": None, "material": None, "genero": None,
        }
        contexto_b = {
            "producto": "polo", "marca": "Lacoste", "talla": "M",
            "color": "azul", "modelo": None, "material": None, "genero": None,
        }

        plan_seguimiento = {
            "producto": None, "marca": None, "talla": None,
            "color": "blanco", "modelo": None, "material": None, "genero": None,
        }

        merged_a = p._merge_atributos(plan_seguimiento, contexto_a)
        merged_b = p._merge_atributos(plan_seguimiento, contexto_b)

        # Cada merge hereda de SU propio contexto, no se mezclan entre si
        assert merged_a["producto"] == "zapatillas"
        assert merged_a["marca"] == "Nike"
        assert merged_a["color"] == "blanco"

        assert merged_b["producto"] == "polo"
        assert merged_b["marca"] == "Lacoste"
        assert merged_b["color"] == "blanco"

        assert merged_a["producto"] != merged_b["producto"]