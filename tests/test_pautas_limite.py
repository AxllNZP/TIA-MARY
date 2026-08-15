"""
Tests de M4: acotar la cantidad de pautas inyectadas en los prompts del
Planner y del Responder, para no consumir el contexto del LLM indefinidamente.
No requieren Ollama.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db
from src.config import MAX_PAUTAS_EN_PROMPT
from src.learning import engine as learning_engine


def _crear_pautas(tipo: str, cantidad: int, prefijo: str) -> list[int]:
    """Crea N pautas de un tipo dado y retorna sus IDs para limpieza posterior."""
    ids = []
    for i in range(cantidad):
        pauta_id = db.guardar_pauta(tipo, f"{prefijo} pauta numero {i}")
        ids.append(pauta_id)
    return ids


def _limpiar_pautas(ids: list[int]) -> None:
    """Elimina pautas de prueba por ID."""
    import sqlite3

    conn = sqlite3.connect(str(db.DATABASE_PATH))
    for pauta_id in ids:
        conn.execute("DELETE FROM pautas WHERE id = ?", (pauta_id,))
    conn.commit()
    conn.close()


class TestLimitePautasPlanner:
    """Pruebas de M4 para get_pautas_planner()."""

    def test_muchas_pautas_solo_llega_subconjunto_acotado(self):
        """Con mas pautas que el limite, solo deben aparecer MAX_PAUTAS_EN_PROMPT."""
        cantidad_creada = MAX_PAUTAS_EN_PROMPT + 5
        ids = _crear_pautas("planner", cantidad_creada, "TEST_M4_PLANNER")

        try:
            texto = learning_engine.get_pautas_planner()
            lineas_de_pauta = [
                l for l in texto.split("\n") if "TEST_M4_PLANNER" in l
            ]
            assert len(lineas_de_pauta) == MAX_PAUTAS_EN_PROMPT
        finally:
            _limpiar_pautas(ids)

    def test_pocas_pautas_se_conservan_todas(self):
        """Con menos pautas que el limite, deben aparecer todas."""
        cantidad_creada = 2
        ids = _crear_pautas("planner", cantidad_creada, "TEST_M4_POCAS")

        try:
            texto = learning_engine.get_pautas_planner()
            lineas_de_pauta = [l for l in texto.split("\n") if "TEST_M4_POCAS" in l]
            assert len(lineas_de_pauta) == cantidad_creada
        finally:
            _limpiar_pautas(ids)

    def test_prioriza_las_mas_recientes(self):
        """Las pautas mas recientes deben aparecer; las mas antiguas del excedente no."""
        cantidad_creada = MAX_PAUTAS_EN_PROMPT + 3
        ids = _crear_pautas("planner", cantidad_creada, "TEST_M4_ORDEN")

        try:
            texto = learning_engine.get_pautas_planner()
            # Las ultimas 3 creadas (indices mas altos) son las MAS recientes
            assert "pauta numero " + str(cantidad_creada - 1) in texto
            # La primera creada (mas antigua) no deberia estar si excede el limite
            assert "pauta numero 0" not in texto
        finally:
            _limpiar_pautas(ids)


class TestLimitePautasResponder:
    """Pruebas de M4 para get_pautas_responder()."""

    def test_muchas_pautas_combinadas_solo_llega_subconjunto(self):
        """responder + general combinadas no deben exceder MAX_PAUTAS_EN_PROMPT."""
        ids_responder = _crear_pautas("responder", MAX_PAUTAS_EN_PROMPT, "TEST_M4_RESP")
        ids_general = _crear_pautas("general", 5, "TEST_M4_GEN")

        try:
            texto = learning_engine.get_pautas_responder()
            lineas_totales = [
                l for l in texto.split("\n")
                if "TEST_M4_RESP" in l or "TEST_M4_GEN" in l
            ]
            assert len(lineas_totales) == MAX_PAUTAS_EN_PROMPT
        finally:
            _limpiar_pautas(ids_responder + ids_general)

    def test_pocas_pautas_combinadas_se_conservan_todas(self):
        """Con pocas pautas de ambos tipos, deben aparecer todas."""
        ids_responder = _crear_pautas("responder", 1, "TEST_M4_RESP_POCAS")
        ids_general = _crear_pautas("general", 1, "TEST_M4_GEN_POCAS")

        try:
            texto = learning_engine.get_pautas_responder()
            assert "TEST_M4_RESP_POCAS" in texto
            assert "TEST_M4_GEN_POCAS" in texto
        finally:
            _limpiar_pautas(ids_responder + ids_general)