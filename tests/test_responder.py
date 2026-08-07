"""
Tests unitarios para el modulo Responder (generador de respuestas).
Incluye tests de un solo turno y tests multi-turno con historial.
"""

import json
import sys
from pathlib import Path

# Asegurar que src este en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.responder import Responder
from src.ollama_client import OllamaClient


class TestResponder:
    """Pruebas de integracion para el Responder (requieren Ollama corriendo)."""

    @pytest.fixture
    def responder(self):
        """Fixture que crea una instancia del Responder."""
        return Responder(nombre_tienda="TIA MARY")

    def test_producto_con_stock(self, responder):
        """Con stock disponible, debe confirmar disponibilidad."""
        respuesta = responder.generate_response(
            mensaje_cliente="Tienen zapatillas Nike?",
            producto_buscado="zapatillas Nike",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 5,
                "variantes_disponibles": None,
            },
        )
        assert len(respuesta) > 0
        # No debe revelar informacion tecnica
        assert "JSON" not in respuesta
        assert "encontrado" not in respuesta.lower()
        assert "TIA MARY" in respuesta.upper() or "Tia Mary" in respuesta

    def test_producto_sin_stock(self, responder):
        """Producto encontrado pero sin stock."""
        respuesta = responder.generate_response(
            mensaje_cliente="Tienen zapatillas Adidas?",
            producto_buscado="zapatillas Adidas",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 0,
                "variantes_disponibles": ["talla 38", "talla 39"],
            },
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta

    def test_producto_no_encontrado(self, responder):
        """Producto no encontrado en inventario."""
        respuesta = responder.generate_response(
            mensaje_cliente="Venden laptops?",
            producto_buscado="laptops",
            resultado_inventario={
                "encontrado": False,
                "cantidad_disponible": None,
                "variantes_disponibles": None,
            },
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta

    def test_respuesta_sin_datos_tecnicos(self, responder):
        """Todas las respuestas deben sonar humanas, sin revelar JSON."""
        respuesta = responder.generate_response(
            mensaje_cliente="Hay polos?",
            producto_buscado="polo",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 2,
                "variantes_disponibles": ["talla M", "talla L"],
            },
        )
        forbidden_terms = [
            "JSON", "encontrado", "cantidad_disponible",
            "variantes_disponibles", "resultado_inventario",
            "base de datos", "consulta", "IA", "modelo",
        ]
        for term in forbidden_terms:
            assert term not in respuesta, f"Termino prohibido '{term}' encontrado en: {respuesta}"

    def test_respuesta_breve(self, responder):
        """La respuesta no debe ser excesivamente larga."""
        respuesta = responder.generate_response(
            mensaje_cliente="Tienen jeans?",
            producto_buscado="jean",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 1,
                "variantes_disponibles": None,
            },
        )
        assert len(respuesta) < 500, f"Respuesta muy larga ({len(respuesta)} chars): {respuesta}"

    def test_resultado_invalido_lanza_error(self, responder):
        """Un resultado sin 'encontrado' debe lanzar ValueError."""
        with pytest.raises(ValueError):
            responder.generate_response(
                mensaje_cliente="test",
                producto_buscado="test",
                resultado_inventario={"cantidad_disponible": 5},
            )


class TestResponderMultiTurn:
    """Pruebas multi-turno para el Responder con historial (requieren Ollama)."""

    @pytest.fixture
    def responder(self):
        """Fixture que crea una instancia del Responder."""
        return Responder(nombre_tienda="TIA MARY")

    def test_respuesta_con_historial_cantidad(self, responder):
        """Con historial, debe responder a 'cuantas unidades quedan?' con cantidad exacta."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": "Si, tenemos 3 unidades disponibles en TIA MARY."},
        ]
        respuesta = responder.generate_response_with_history(
            system_prompt=responder.system_prompt,
            mensaje_cliente="cuantas unidades quedan?",
            producto_buscado="zapatillas Nike talla 42",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 3,
                "variantes_disponibles": None,
            },
            history=history,
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta
        # Debe mencionar el numero 3 (cantidad)
        assert "3" in respuesta

    def test_respuesta_con_historial_precio(self, responder):
        """Con historial, debe responder a 'cuanto cuesta?' mencionando precio."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": "Si, tenemos 3 unidades disponibles en TIA MARY."},
        ]
        respuesta = responder.generate_response_with_history(
            system_prompt=responder.system_prompt,
            mensaje_cliente="cuanto cuesta?",
            producto_buscado="zapatillas Nike talla 42",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 3,
                "variantes_disponibles": None,
            },
            history=history,
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta

    def test_respuesta_con_historial_variantes(self, responder):
        """Con historial, debe responder a 'y de otra talla?' ofreciendo variantes."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": "Si, tenemos 3 unidades disponibles en TIA MARY."},
        ]
        respuesta = responder.generate_response_with_history(
            system_prompt=responder.system_prompt,
            mensaje_cliente="y de otra talla?",
            producto_buscado="zapatillas Nike",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 8,
                "variantes_disponibles": ["Nike - talla 40 - color negro", "Nike - talla 42 - color negro"],
            },
            history=history,
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta

    def test_respuesta_sin_historial_funciona(self, responder):
        """generate_response_with_history debe funcionar sin historial."""
        respuesta = responder.generate_response_with_history(
            system_prompt=responder.system_prompt,
            mensaje_cliente="Tienen zapatillas Nike?",
            producto_buscado="zapatillas Nike",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 5,
                "variantes_disponibles": None,
            },
            history=None,
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta

    def test_respuesta_con_historial_mantiene_contexto(self, responder):
        """La respuesta con historial debe mencionar el producto del contexto."""
        history = [
            {"role": "user", "content": "Tienen polos azules?"},
            {"role": "assistant", "content": "Si, tenemos Lacoste y Tommy Hilfiger en azul."},
        ]
        respuesta = responder.generate_response_with_history(
            system_prompt=responder.system_prompt,
            mensaje_cliente="el Lacoste en talla L?",
            producto_buscado="polo Lacoste talla L",
            resultado_inventario={
                "encontrado": True,
                "cantidad_disponible": 2,
                "variantes_disponibles": ["Lacoste - talla L - color azul", "Lacoste - talla M - color azul"],
            },
            history=history,
        )
        assert len(respuesta) > 0
        assert "JSON" not in respuesta
        # No debe revelar datos tecnicos
        forbidden = ["encontrado", "cantidad_disponible", "variantes_disponibles"]
        for term in forbidden:
            assert term not in respuesta, f"Termino prohibido '{term}' en: {respuesta}"