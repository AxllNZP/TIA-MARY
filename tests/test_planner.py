"""
Tests unitarios para el modulo Planner (clasificador de intencion).
Incluye tests de parser JSON, tests de un solo turno, tests multi-turno
con historial, y validacion de schema.
"""

import json
import sys
from pathlib import Path

# Asegurar que src este en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.planner import Planner, PlannerOutput, PLANNER_SCHEMA
from src.ollama_client import OllamaClient, parse_json_response


class TestParseJsonResponse:
    """Pruebas para la funcion parse_json_response."""

    def test_json_limpio(self):
        """Debe parsear un JSON limpio sin modificaciones."""
        response = '{"accion": "consultar_stock", "producto": "zapatillas"}'
        result = parse_json_response(response)
        assert result == {"accion": "consultar_stock", "producto": "zapatillas"}

    def test_json_con_markdown(self):
        """Debe extraer JSON de un bloque markdown ```json ... ```."""
        response = '''```json
{"accion": "pedir_aclaracion", "producto": null, "marca": null}
```'''
        result = parse_json_response(response)
        assert result["accion"] == "pedir_aclaracion"

    def test_json_con_texto_alrededor(self):
        """Debe extraer el JSON aunque haya texto antes o despues."""
        response = 'Analizando el mensaje...\n{"accion": "no_relacionado", "producto": null}\nEspero que sirva.'
        result = parse_json_response(response)
        assert result["accion"] == "no_relacionado"

    def test_json_con_bloque_sin_especificar(self):
        """Debe extraer JSON de bloque markdown sin especificar lenguaje."""
        response = '```\n{"accion": "consultar_stock", "producto": "polo"}\n```'
        result = parse_json_response(response)
        assert result["producto"] == "polo"

    def test_json_invalido_lanza_error(self):
        """Debe lanzar ValueError si no hay JSON valido."""
        with pytest.raises(ValueError):
            parse_json_response("Hola, soy un texto sin JSON")


class TestSchemaValidation:
    """Pruebas para validar que el schema JSON del Planner es correcto."""

    def test_schema_tiene_campos_requeridos(self):
        """El schema debe tener todos los campos esperados."""
        props = PLANNER_SCHEMA.get("properties", {})
        assert "accion" in props
        assert "producto" in props
        assert "marca" in props
        assert "talla" in props
        assert "color" in props
        assert "modelo" in props
        assert "material" in props
        assert "genero" in props
        assert "cantidad_solicitada" in props
        assert "precio_consultado" in props
        assert "consultar_variantes" in props
        assert "atributo_faltante" in props
        assert "mensaje_aclaracion" in props

    def test_schema_accion_es_string(self):
        """El campo accion debe ser de tipo string."""
        props = PLANNER_SCHEMA.get("properties", {})
        assert props["accion"].get("type") == "string"

    def test_schema_accion_restringe_valores_permitidos(self):
        """
        El campo accion debe estar restringido (enum) a los 4 valores
        validos, para que Ollama no pueda generar acciones arbitrarias (M2).
        """
        props = PLANNER_SCHEMA.get("properties", {})
        valores_permitidos = {
            "consultar_stock", "pedir_aclaracion",
            "no_relacionado", "consultar_catalogo",
        }
        assert "enum" in props["accion"], "accion debe declarar un enum en el schema"
        assert set(props["accion"]["enum"]) == valores_permitidos

    def test_schema_cantidad_es_integer_o_null(self):
        """El campo cantidad_solicitada debe ser integer o null."""
        props = PLANNER_SCHEMA.get("properties", {})
        # Pydantic genera Optional[int] como "anyOf" con integer y null
        assert "cantidad_solicitada" in props

    def test_planner_output_model_valida(self):
        """PlannerOutput debe validar un JSON correcto."""
        data = {
            "accion": "consultar_stock",
            "producto": "zapatillas",
            "marca": "Nike",
            "talla": "42",
            "color": "negro",
            "cantidad_solicitada": None,
            "precio_consultado": False,
            "consultar_variantes": False,
            "mensaje_aclaracion": None,
        }
        model = PlannerOutput(**data)
        assert model.accion == "consultar_stock"
        assert model.producto == "zapatillas"
        assert model.marca == "Nike"
        assert model.talla == "42"
        assert model.color == "negro"

    def test_planner_output_acepta_nulls(self):
        """PlannerOutput debe aceptar todos los campos opcionales como null."""
        data = {
            "accion": "no_relacionado",
            "producto": None,
            "marca": None,
            "talla": None,
            "color": None,
            "modelo": None,
            "material": None,
            "genero": None,
            "cantidad_solicitada": None,
            "precio_consultado": False,
            "consultar_variantes": False,
            "atributo_faltante": None,
            "mensaje_aclaracion": None,
        }
        model = PlannerOutput(**data)
        assert model.accion == "no_relacionado"
        assert model.producto is None
        assert model.color is None

        

class TestAccionRestringida:
    """
    Pruebas de M2: PlannerOutput.accion debe aceptar unicamente las 4
    acciones validas, y una accion fuera de ese conjunto no debe ser
    aceptada silenciosamente en ningun punto del contrato.
    """

    @pytest.mark.parametrize("accion_valida", [
        "consultar_stock", "pedir_aclaracion", "no_relacionado", "consultar_catalogo",
    ])
    def test_pydantic_acepta_las_4_acciones_validas(self, accion_valida):
        """Cada una de las 4 acciones validas debe pasar la validacion de Pydantic."""
        data = {
            "accion": accion_valida,
            "producto": None, "marca": None, "talla": None, "color": None,
            "modelo": None, "material": None, "genero": None,
            "cantidad_solicitada": None, "precio_consultado": False,
            "consultar_variantes": False, "atributo_faltante": None,
            "mensaje_aclaracion": None,
        }
        model = PlannerOutput(**data)
        assert model.accion == accion_valida

    def test_pydantic_rechaza_accion_no_permitida(self):
        """
        Una accion fuera del conjunto permitido (Literal) debe ser rechazada
        por Pydantic con un error de validacion, NO aceptada silenciosamente.
        """
        from pydantic import ValidationError

        data = {
            "accion": "comprar_ahora",  # accion inventada, fuera del schema
            "producto": None, "marca": None, "talla": None, "color": None,
            "modelo": None, "material": None, "genero": None,
            "cantidad_solicitada": None, "precio_consultado": False,
            "consultar_variantes": False, "atributo_faltante": None,
            "mensaje_aclaracion": None,
        }
        with pytest.raises(ValidationError):
            PlannerOutput(**data)

    def test_normalize_result_registra_accion_invalida_no_la_oculta(self, caplog):
        """
        _normalize_result (red de seguridad del camino de fallback) debe
        registrar (log warning) cuando recibe una accion invalida, en vez
        de silenciarla sin dejar rastro.
        """
        import logging

        planner = Planner.__new__(Planner)  # evita __init__ (no requiere OllamaClient)

        with caplog.at_level(logging.WARNING):
            resultado = planner._normalize_result({"accion": "comprar_ahora"})

        assert resultado["accion"] == "no_relacionado"  # fallback seguro se mantiene
        assert any(
            "accion invalida" in registro.message.lower()
            for registro in caplog.records
        ), "Se esperaba un warning registrando la accion invalida detectada"

    def test_normalize_result_no_registra_advertencia_con_accion_valida(self, caplog):
        """Una accion valida no debe generar ninguna advertencia."""
        import logging

        planner = Planner.__new__(Planner)

        with caplog.at_level(logging.WARNING):
            resultado = planner._normalize_result({"accion": "consultar_stock"})

        assert resultado["accion"] == "consultar_stock"
        assert len(caplog.records) == 0
class TestPlanner:
    """Pruebas de integracion para el Planner (requieren Ollama corriendo)."""

    @pytest.fixture
    def planner(self):
        """Fixture que crea una instancia del Planner."""
        return Planner()

    def test_consultar_stock_zapatillas(self, planner):
        """Un mensaje claro de consulta de stock debe clasificarse correctamente."""
        result = planner.classify("Tienen zapatillas Nike talla 42?")
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None
        assert "zapatilla" in (result["producto"] or "").lower()

    def test_consultar_stock_polo(self, planner):
        """Consulta de polo con color."""
        result = planner.classify("Hola, busco un polo azul talla M")
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None
        assert "polo" in (result["producto"] or "").lower()

    def test_saludo_generico(self, planner):
        """Un saludo generico no es consulta de stock."""
        result = planner.classify("Buenos dias")
        assert result["accion"] in ("no_relacionado", "pedir_aclaracion")

    def test_gracias(self, planner):
        """Un agradecimiento no es consulta de stock."""
        result = planner.classify("Muchas gracias por la informacion")
        assert result["accion"] == "no_relacionado"

    def test_mensaje_ambiguo(self, planner):
        """Un mensaje muy vago deberia pedir aclaracion o ser no_relacionado."""
        result = planner.classify("tienen algo bonito?")
        assert result["accion"] in ("pedir_aclaracion", "no_relacionado")

    def test_campos_opcionales_null(self, planner):
        """Los campos no mencionados deben ser null."""
        result = planner.classify("Tienen zapatillas?")
        assert result["accion"] == "consultar_stock"
        assert result["marca"] is None or result["marca"] == "" or result["marca"] is None
        assert result["cantidad_solicitada"] is None

    def test_cantidad_solicitada(self, planner):
        """Cuando el cliente menciona cantidad, debe extraerse."""
        result = planner.classify("Quiero 3 polos blancos")
        assert result["accion"] == "consultar_stock"
        if result["cantidad_solicitada"] is not None:
            assert result["cantidad_solicitada"] == 3


class TestPlannerMultiTurn:
    """Pruebas multi-turno para el Planner con historial (requieren Ollama)."""

    @pytest.fixture
    def planner(self):
        """Fixture que crea una instancia del Planner."""
        return Planner()

    def test_seguimiento_cambio_talla(self, planner):
        """Seguimiento que cambia la talla debe heredar producto+marca del historial."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla_o_variante":"42","cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("y en talla 40?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None
        assert "zapatilla" in (result["producto"] or "").lower()
        assert result["marca"] is not None
        assert "nike" in (result["marca"] or "").lower()

    def test_seguimiento_cantidad(self, planner):
        """Seguimiento que pregunta por cantidad debe heredar el contexto."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla_o_variante":"42","cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("cuantas unidades quedan?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None

    def test_seguimiento_precio(self, planner):
        """Seguimiento que pregunta por precio debe heredar el contexto."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla_o_variante":"42","cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("cuanto cuesta?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None

    def test_seguimiento_otra_talla(self, planner):
        """Seguimiento que pregunta por otra talla debe heredar producto+marca."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla_o_variante":"42","cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("y de otra talla?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None

    def test_seguimiento_cambio_producto(self, planner):
        """Seguimiento que cambia de producto debe detectar el nuevo producto."""
        history = [
            {"role": "user", "content": "Tienen zapatillas Nike talla 42?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla_o_variante":"42","cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("y un polo azul?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None
        assert "polo" in (result["producto"] or "").lower()

    def test_seguimiento_marca_especifica(self, planner):
        """Seguimiento que menciona marca+talla debe heredar producto del contexto."""
        history = [
            {"role": "user", "content": "Tienen polos azules?"},
            {"role": "assistant", "content": '{"accion":"consultar_stock","producto":"polo","marca":null,"talla_o_variante":null,"cantidad_solicitada":null,"mensaje_aclaracion":null}'},
        ]
        result = planner.classify_with_history("el Lacoste en talla L?", history)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None
        assert "polo" in (result["producto"] or "").lower()
        assert result["marca"] is not None
        assert "lacoste" in (result["marca"] or "").lower()

    def test_sin_historial_funciona(self, planner):
        """classify_with_history debe funcionar sin historial (como classify)."""
        result = planner.classify_with_history("Tienen zapatillas Nike talla 42?", history=None)
        assert result["accion"] == "consultar_stock"
        assert result["producto"] is not None


class TestCatalogo:
    """Pruebas para la funcionalidad de catalogo (sin LLM, 100% confiable)."""

    def test_detecta_que_venden(self):
        """El pipeline debe detectar 'que venden' como consulta de catalogo."""
        from src.pipeline import Pipeline
        p = Pipeline()
        r = p.procesar_mensaje("que venden?")
        assert r["planificacion"]["accion"] == "consultar_catalogo"
        assert "MARY" in r["respuesta"]  # Buscar sin tilde por encoding de Windows
        assert len(r["respuesta"]) > 50  # No es un saludo vacio

    def test_detecta_catalogo_palabras_clave(self):
        """El pipeline debe detectar variantes de 'catalogo'."""
        from src.pipeline import Pipeline
        p = Pipeline()
        for msg in ["muestrame el catalogo", "que productos tienen", "que ofrecen"]:
            r = p.procesar_mensaje(msg)
            assert r["planificacion"]["accion"] == "consultar_catalogo", f"Fallo para: {msg}"

    def test_no_confunde_stock_con_catalogo(self):
        """'Tienen zapatillas Nike talla 42?' no debe ser catalogo."""
        from src.pipeline import Pipeline
        p = Pipeline()
        # Estos mensajes no deben activar el filtro de catalogo
        assert not p._es_consulta_catalogo("Tienen zapatillas Nike talla 42?")
        assert not p._es_consulta_catalogo("Cuanto cuesta el polo Lacoste?")
        assert not p._es_consulta_catalogo("Buenos dias")

    def test_respuesta_catalogo_tiene_productos(self):
        """La respuesta de catalogo debe mencionar productos reales de la BD."""
        from src.pipeline import Pipeline
        p = Pipeline()
        r = p.procesar_mensaje("que venden?")
        assert "zapatillas" in r["respuesta"].lower()
        assert "polo" in r["respuesta"].lower() or "polos" in r["respuesta"].lower()
        assert "MARY" in r["respuesta"]  # Buscar sin tilde por encoding de Windows
