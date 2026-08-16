"""
Tests de integracion end-to-end para seguimiento conversacional.

Diferencia clave con tests/test_planner.py::TestPlannerMultiTurn:
- TestPlannerMultiTurn prueba Planner.classify_with_history() EN AISLAMIENTO.
  El Planner (LLM de 8B) puede fallar en resolver referencias contextuales
  complejas en algunos casos — es una limitacion conocida y documentada.
- Esta suite prueba Pipeline.procesar_mensaje() COMPLETO, que es lo que
  realmente determina la respuesta que recibe el cliente. El pipeline tiene
  dos mecanismos de compensacion construidos en fases anteriores:
    1. _merge_atributos(): hereda producto/marca/talla/color del contexto
       de sesion en CODIGO, sin depender de que el LLM acierte.
    2. _fallback_seguimiento() (A4): si el Planner clasifica mal como
       no_relacionado, detecta el patron de seguimiento por heuristica y
       reconsulta el inventario real con el contexto heredado.

Estos tests documentan que, incluso cuando el Planner aislado falla (ver
TestPlannerMultiTurn), el cliente final recibe la respuesta correcta.
Requieren Ollama corriendo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import Pipeline


class TestSeguimientoEndToEnd:
    """
    Verifica la respuesta real al cliente en escenarios de seguimiento,
    a traves del pipeline completo (no del Planner aislado).
    """

    def test_seguimiento_precio_responde_precio_correcto(self):
        """
        Escenario de test_planner.py::test_seguimiento_precio (falla en
        aislamiento). End-to-end, el cliente debe recibir el precio real.
        """
        pipeline = Pipeline()
        session_id = "test_e2e_precio"

        pipeline.procesar_mensaje("Tienen zapatillas Nike talla 42?", session_id=session_id)
        resultado = pipeline.procesar_mensaje("cuanto cuesta?", session_id=session_id)

        assert "250" in resultado["respuesta"]

    def test_seguimiento_cantidad_responde_stock_correcto(self):
        """
        Escenario de test_planner.py::test_seguimiento_cantidad (falla en
        aislamiento). End-to-end, el cliente debe recibir el stock real.
        """
        pipeline = Pipeline()
        session_id = "test_e2e_cantidad"

        pipeline.procesar_mensaje("Tienen zapatillas Nike talla 42?", session_id=session_id)
        resultado = pipeline.procesar_mensaje("cuantas unidades quedan?", session_id=session_id)

        assert "3" in resultado["respuesta"]

    def test_seguimiento_solo_marca_responde_producto_correcto(self):
        """
        Escenario de test_planner.py::test_seguimiento_marca_especifica
        (falla en aislamiento: el Planner confunde marca con producto).
        End-to-end, el cliente debe recibir informacion del polo Lacoste
        talla L (no un error ni una respuesta sobre "Lacoste" como producto).
        """
        pipeline = Pipeline()
        session_id = "test_e2e_marca"

        pipeline.procesar_mensaje("Tienen polos azules?", session_id=session_id)
        resultado = pipeline.procesar_mensaje("el Lacoste en talla L?", session_id=session_id)

        respuesta_lower = resultado["respuesta"].lower()
        assert "lacoste" in respuesta_lower
        assert "polo" in respuesta_lower or "120" in resultado["respuesta"]
        # No debe ser un mensaje de "no encontrado" o error
        assert "no manejamos" not in respuesta_lower
        assert "no encontre" not in respuesta_lower