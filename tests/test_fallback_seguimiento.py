"""
Tests para _fallback_seguimiento (A4).
Verifican que el fallback reconstruye el plan con prioridad al dato nuevo
del mensaje sobre el contexto heredado, y que SIEMPRE vuelve a consultar
consultar_stock() en vez de reutilizar memoria estatica del contexto.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import Pipeline
from src import database as db


class TestFallbackSeguimiento:
    """Pruebas del fallback de emergencia con reconsulta real a inventario."""

    @classmethod
    def setup_class(cls):
        db.init_db()
        db.seed_from_json()

    def test_reconsulta_inventario_es_llamada(self):
        """
        Verifica explicitamente que consultar_stock() es invocado de nuevo
        por el fallback (no se reutiliza memoria estatica del contexto).
        """
        pipeline = Pipeline()
        contexto = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": None, "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        }

        with patch("src.pipeline.consultar_stock", wraps=None) as mock_consultar:
            mock_consultar.return_value = {
                "encontrado": True, "cantidad_disponible": 8,
                "precio": 250.0, "variantes_disponibles": None,
            }
            pipeline._fallback_seguimiento("y en talla 40?", contexto)

        mock_consultar.assert_called_once()
        plan_usado = mock_consultar.call_args[0][0]
        assert plan_usado["talla"] == "40"  # dato nuevo, NO el heredado (42)
        assert plan_usado["marca"] == "Nike"  # heredado, se conserva

    def test_talla_nueva_tiene_prioridad_sobre_heredada(self):
        """
        Caso central del prompt: contexto tiene talla=42, mensaje pide
        talla 40. El plan reconstruido debe usar 40, nunca 42.
        """
        pipeline = Pipeline()
        contexto = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": "negro", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        }

        resultado = pipeline._fallback_seguimiento("y en talla 40?", contexto)

        assert resultado["planificacion"]["talla"] == "40"
        assert resultado["planificacion"]["talla"] != "42"

    def test_stock_real_no_reutiliza_valor_antiguo_del_contexto(self):
        """
        Integracion real (sin mock) contra la BD semilla, replicando el
        ejemplo del prompt: Nike talla 42 -> stock 3, talla 40 -> stock 5.
        El fallback debe responder con el stock de la talla 40 (nueva),
        NUNCA con el stock guardado en el contexto (talla 42 = 3).
        """
        pipeline = Pipeline()
        contexto = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": "negro", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        }

        resultado = pipeline._fallback_seguimiento("cuantas unidades en talla 40?", contexto)

        assert resultado["inventario"]["encontrado"] is True
        # id=1 en seed_productos.json: zapatillas Nike talla 40 color negro, stock=5
        assert resultado["inventario"]["cantidad_disponible"] == 5
        assert resultado["inventario"]["cantidad_disponible"] != 3
        assert "5" in resultado["respuesta"]

    def test_color_nuevo_tiene_prioridad_sobre_heredado(self):
        """El mensaje puede cambiar el color; debe tener prioridad sobre el contexto."""
        pipeline = Pipeline()
        contexto = {
            "producto": "medias", "marca": "Puma", "talla": None,
            "color": "blanco", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 20, "variantes": None, "precio": 25.0,
        }

        resultado = pipeline._fallback_seguimiento("y en negro?", contexto)

        assert resultado["planificacion"]["color"] == "negro"
        # id=16 en seed_productos.json: medias Puma color negro, stock=15
        assert resultado["inventario"]["cantidad_disponible"] == 15
        assert resultado["inventario"]["cantidad_disponible"] != 20

    def test_sin_atributo_nuevo_hereda_contexto_y_reconsulta_igual(self):
        """
        Si el mensaje no menciona talla/color nuevos, se hereda del contexto,
        pero AUN ASI se debe reconsultar consultar_stock() (no usar memoria).
        """
        pipeline = Pipeline()
        contexto = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": "negro", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        }

        with patch("src.pipeline.consultar_stock") as mock_consultar:
            mock_consultar.return_value = {
                "encontrado": True, "cantidad_disponible": 3,
                "precio": 250.0, "variantes_disponibles": None,
            }
            pipeline._fallback_seguimiento("cuantas unidades quedan?", contexto)

        mock_consultar.assert_called_once()
        plan_usado = mock_consultar.call_args[0][0]
        assert plan_usado["talla"] == "42"  # heredado, sin dato nuevo en el mensaje

    def test_talla_inexistente_no_encuentra_y_no_inventa_stock(self):
        """Si la nueva talla no existe en BD, debe reportar no encontrado, sin inventar stock."""
        pipeline = Pipeline()
        contexto = {
            "producto": "zapatillas", "marca": "Nike", "talla": "42",
            "color": "negro", "modelo": None, "material": None, "genero": None,
            "cantidad_disponible": 3, "variantes": None, "precio": 250.0,
        }

        resultado = pipeline._fallback_seguimiento("y en talla 99?", contexto)

        assert resultado["inventario"]["encontrado"] is False