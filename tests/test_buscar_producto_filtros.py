"""
Tests de integridad de filtros para database.py::buscar_producto (A3).
Verifican que solo se suma stock de filas que coinciden EXACTAMENTE con
todos los filtros especificados, sin inflar el total con filas parciales.
No requieren Ollama.

Referencia de datos semilla usados (data/seed_productos.json):
  id=1  zapatillas Nike talla=40 color=negro  stock=5
  id=2  zapatillas Nike talla=42 color=negro  stock=3
  id=3  zapatillas Nike talla=38 color=blanco stock=0
  id=15 medias Puma talla=unica color=blanco  stock=20
  id=16 medias Puma talla=unica color=negro   stock=15
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db


class TestBuscarProductoFiltros:
    """Pruebas de coincidencia exacta de filtros en buscar_producto."""

    @classmethod
    def setup_class(cls):
        """Asegura que la BD este inicializada con los datos semilla."""
        db.init_db()
        db.seed_from_json()

    def test_1_solo_marca(self):
        """Solo marca: debe sumar TODAS las filas Nike de zapatillas (5+3+0=8)."""
        result = db.buscar_producto(nombre="zapatillas", marca="Nike")
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 8

    def test_2_marca_mas_color(self):
        """Marca + color: solo filas Nike + negro (id 1 y 2 -> 5+3=8)."""
        result = db.buscar_producto(nombre="zapatillas", marca="Nike", color="negro")
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 8

    def test_3_marca_mas_talla(self):
        """Marca + talla: solo la fila Nike talla 42 (id 2 -> stock 3)."""
        result = db.buscar_producto(nombre="zapatillas", marca="Nike", talla="42")
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 3

    def test_4_marca_color_talla_caso_del_prompt(self):
        """
        Caso critico del prompt: marca=Nike, color=negro, talla=42.
        Solo debe coincidir la fila id=2 (stock=3). NO debe sumar la fila
        id=1 (talla 40, tambien negro) ni la id=3 (talla 38, blanco).
        Resultado esperado: 3, NUNCA 8.
        """
        result = db.buscar_producto(
            nombre="zapatillas", marca="Nike", color="negro", talla="42"
        )
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 3
        assert result["cantidad_disponible"] != 8

    def test_5_filtro_sin_coincidencias(self):
        """Un filtro que no tiene ninguna fila coincidente (color inexistente)."""
        result = db.buscar_producto(nombre="zapatillas", marca="Nike", color="verde")
        assert result["encontrado"] is False
        assert result["cantidad_disponible"] is None

    def test_6_multiples_filas_coincidencia_exacta(self):
        """
        Multiples filas que SI coinciden con todos los filtros especificados
        deben sumarse correctamente (medias Puma, ambos colores -> 20+15=35).
        """
        result = db.buscar_producto(nombre="medias", marca="Puma")
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 35

    def test_7_filas_parciales_no_deben_sumar(self):
        """
        Filas que coinciden con SOLO parte de los filtros (ej. misma marca
        y color pero distinta talla) no deben contribuir al stock cuando
        la talla fue especificada explicitamente.
        """
        # Nike + negro + talla 40 -> solo id=1 (stock=5), NO debe incluir id=2 (talla 42)
        result = db.buscar_producto(
            nombre="zapatillas", marca="Nike", color="negro", talla="40"
        )
        assert result["encontrado"] is True
        assert result["cantidad_disponible"] == 5

        # Puma + color blanco -> solo id=15 (stock=20), NO debe incluir id=16 (negro)
        result_color = db.buscar_producto(nombre="medias", marca="Puma", color="blanco")
        assert result_color["encontrado"] is True
        assert result_color["cantidad_disponible"] == 20

    def test_fallback_respeta_filtros_no_solo_nombre(self):
        """
        Regresion critica: cuando la busqueda exacta no matchea (ej. talla
        inexistente) y se activa el fallback de nombre parcial, los filtros
        marca/color ya especificados deben seguir aplicandose. No debe
        devolver stock de otras marcas o colores.
        """
        # Nike + negro + talla 99 (no existe) -> el fallback NO debe devolver
        # zapatillas Adidas ni de otro color como si coincidieran.
        result = db.buscar_producto(
            nombre="zapatillas", marca="Nike", color="negro", talla="99"
        )
        # No debe encontrar coincidencia exacta de talla 99, y el fallback
        # (que ahora respeta marca+color) tampoco debe inventar una.
        if result["encontrado"]:
            assert result["cantidad_disponible"] in (5, 3, 8)  # solo Nike+negro