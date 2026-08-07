"""
Modulo Planificador: Clasificador de intencion de mensajes de WhatsApp.
Analiza el mensaje del cliente y extrae entidades estructuradas (NO genera lenguaje natural).
Decide que accion debe tomar el sistema:
- consultar_stock: buscar disponibilidad de un producto
- pedir_aclaracion: solicitar mas informacion al cliente
- no_relacionado: mensaje que no es una consulta de stock
"""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .config import PROMPT_DIR, PLANNER_PROMPT_FILE, OLLAMA_NUM_PREDICT_PLANNER
from .ollama_client import OllamaClient, parse_json_response


# Prompt por defecto del planificador (tambien se puede cargar desde archivo)
PLANNER_SYSTEM_PROMPT = """Eres el modulo de planificacion de un asistente de WhatsApp para una tienda de ropa y calzado llamada TIA MARY.
Tu unica tarea es analizar el mensaje del cliente y extraer entidades estructuradas. NO respondes al cliente directamente. NO generas lenguaje natural.

Debes devolver EXCLUSIVAMENTE un JSON con esta estructura, sin texto adicional, sin markdown:

{
  "accion": "consultar_stock" | "pedir_aclaracion" | "no_relacionado",
  "producto": "string o null",
  "marca": "string o null",
  "talla": "string o null",
  "color": "string o null",
  "modelo": "string o null",
  "material": "string o null",
  "genero": "string o null",
  "cantidad_solicitada": "number o null",
  "precio_consultado": "boolean",
  "consultar_variantes": "boolean",
  "atributo_faltante": "string o null",
  "mensaje_aclaracion": "string o null"
}

IMPORTANTE: 
- El campo "producto" debe contener SOLO el tipo de producto (ej: "zapatillas", "polo", "jean", "medias", "gorra", "casaca").
- NUNCA pongas la marca dentro de "producto". La marca va EXCLUSIVAMENTE en el campo "marca".
- "precio_consultado" es true si el cliente pregunta por precio, costo, o cuanto cuesta.
- "consultar_variantes" es true si el cliente pregunta que tallas/colores/modelos hay disponibles.
- "atributo_faltante" indica que atributo falta cuando accion es "pedir_aclaracion" (ej: "marca", "talla", "color").
- "mensaje_aclaracion" debe ser SOLO una pregunta breve y directa. No generes parrafos.
- NO uses acentos ni caracteres especiales en el JSON de salida.
- Todos los campos booleanos deben ser true o false (no null).

Ejemplos de mensajes aislados (sin historial):
- "Tienen zapatillas Nike talla 42?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"42","color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Busco un polo azul talla M" -> {"accion":"consultar_stock","producto":"polo","marca":null,"talla":"M","color":"azul","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Zapatillas Adidas" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Adidas","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Tienen medias Puma?" -> {"accion":"consultar_stock","producto":"medias","marca":"Puma","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Buenos dias" -> {"accion":"no_relacionado","producto":null,"marca":null,"talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Cuanto cuesta el polo Lacoste?" -> {"accion":"consultar_stock","producto":"polo","marca":"Lacoste","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":true,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "Que tallas tienen de zapatillas Nike?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":true,"atributo_faltante":null,"mensaje_aclaracion":null}

Ejemplos de SEGUIMIENTO (con historial previo en la conversacion):

Conversacion previa:
  Cliente: "Tienen zapatillas Nike talla 42?"
  Asistente: "Si, tenemos 3 unidades disponibles..."

Nuevos mensajes posibles del cliente:
- "y en talla 40?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"40","color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "cuantas unidades quedan?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"42","color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "y en blanco?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"42","color":"blanco","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "solo negro?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"42","color":"negro","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "cuanto cuesta?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":"42","color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":true,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "y de otra talla cuanto cuestan?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":true,"consultar_variantes":true,"atributo_faltante":null,"mensaje_aclaracion":null}
- "y un polo azul?" -> {"accion":"consultar_stock","producto":"polo","marca":null,"talla":null,"color":"azul","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "que tallas tienen?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":true,"atributo_faltante":null,"mensaje_aclaracion":null}
- "de que colores?" -> {"accion":"consultar_stock","producto":"zapatillas","marca":"Nike","talla":null,"color":null,"modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":true,"atributo_faltante":null,"mensaje_aclaracion":null}

Conversacion previa:
  Cliente: "Tienen polos azules?"
  Asistente: "Si, tenemos Lacoste y Tommy Hilfiger en azul..."

Nuevos mensajes posibles del cliente:
- "el Lacoste en talla L?" -> {"accion":"consultar_stock","producto":"polo","marca":"Lacoste","talla":"L","color":"azul","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":false,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}
- "cuanto cuesta el Tommy?" -> {"accion":"consultar_stock","producto":"polo","marca":"Tommy Hilfiger","talla":null,"color":"azul","modelo":null,"material":null,"genero":null,"cantidad_solicitada":null,"precio_consultado":true,"consultar_variantes":false,"atributo_faltante":null,"mensaje_aclaracion":null}

Reglas:
1. Si el cliente pregunta por disponibilidad de un producto (aunque sea informal, con errores o incompleto), usa "accion": "consultar_stock" y extrae la mayor informacion posible en los campos correspondientes. Si un dato no se menciona, ponlo en null.
2. Si el mensaje es ambiguo y no permite identificar que producto busca, usa "accion": "pedir_aclaracion" e indica en "atributo_faltante" que dato falta (ej: "marca", "talla", "color").
3. Si el mensaje no tiene relacion con consultar stock (saludo generico, queja, agradecimiento, etc.), usa "accion": "no_relacionado".
4. Nunca inventes datos de inventario. Tu trabajo es solo extraer entidades del mensaje del cliente.
5. Responde siempre en el mismo idioma del cliente (por defecto, espanol).
6. Si el mensaje es de seguimiento (se refiere a un producto mencionado antes en la conversacion), usa la informacion del historial para completar los campos. El producto, marca, talla y color pueden heredarse del contexto. Si el cliente menciona un nuevo atributo, actualiza ese campo. Si el cliente cambia de producto, usa el nuevo producto.
7. NO generes lenguaje natural en los campos de entidades. Los campos deben contener solo valores extraidos del mensaje o heredados del historial.
"""


class PlannerOutput(BaseModel):
    """
    Modelo Pydantic que define la estructura del JSON de salida del Planner.
    Se usa para generar el JSON Schema que se pasa al parametro `format` de Ollama.
    Solo extraccion de entidades — NO genera lenguaje natural.
    """
    accion: str = Field(
        description="consultar_stock | pedir_aclaracion | no_relacionado | consultar_catalogo"
    )
    producto: Optional[str] = Field(
        default=None,
        description="Tipo de producto (zapatillas, polo, jean, medias, gorra, casaca)"
    )
    marca: Optional[str] = Field(
        default=None,
        description="Marca del producto (Nike, Adidas, Lacoste, etc.)"
    )
    talla: Optional[str] = Field(
        default=None,
        description="Talla (42, M, L, unica, etc.)"
    )
    color: Optional[str] = Field(
        default=None,
        description="Color del producto (negro, blanco, azul, rojo, etc.)"
    )
    modelo: Optional[str] = Field(
        default=None,
        description="Modelo especifico del producto si se menciona"
    )
    material: Optional[str] = Field(
        default=None,
        description="Material del producto (algodon, cuero, etc.)"
    )
    genero: Optional[str] = Field(
        default=None,
        description="Genero (hombre, mujer, nino, unisex)"
    )
    cantidad_solicitada: Optional[int] = Field(
        default=None,
        description="Cantidad solicitada por el cliente (numero)"
    )
    precio_consultado: bool = Field(
        default=False,
        description="True si el cliente pregunta por precio o costo"
    )
    consultar_variantes: bool = Field(
        default=False,
        description="True si el cliente pregunta que tallas/colores/modelos hay"
    )
    atributo_faltante: Optional[str] = Field(
        default=None,
        description="Que atributo falta cuando accion es pedir_aclaracion"
    )
    mensaje_aclaracion: Optional[str] = Field(
        default=None,
        description="Pregunta breve de aclaracion (solo si accion es pedir_aclaracion)"
    )


# JSON Schema generado desde el modelo Pydantic
PLANNER_SCHEMA = PlannerOutput.model_json_schema()


class Planner:
    """
    Clasificador de intencion para mensajes de clientes de WhatsApp.
    Usa Ollama para interpretar lenguaje natural y extraer la intencion de compra.
    Soporta historial de conversacion para preguntas de seguimiento.
    """

    def __init__(self, client: Optional[OllamaClient] = None):
        """
        Args:
            client: Cliente de Ollama. Si no se provee, se crea uno con defaults.
        """
        self.client = client or OllamaClient()
        self.system_prompt = self._load_system_prompt()
        self.schema = PLANNER_SCHEMA

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo o usa el prompt por defecto."""
        prompt_path = Path(PROMPT_DIR) / PLANNER_PROMPT_FILE
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return PLANNER_SYSTEM_PROMPT

    def classify(self, mensaje: str) -> dict:
        """
        Clasifica un mensaje de cliente y extrae la intencion.
        Usa el system prompt por defecto (o cargado desde archivo).
        Sin historial (retrocompatible con tests existentes).

        Args:
            mensaje: Texto del cliente desde WhatsApp.

        Returns:
            Diccionario con la clasificacion.
        """
        return self.classify_with_prompt(self.system_prompt, mensaje)

    def classify_with_prompt(self, system_prompt: str, mensaje: str) -> dict:
        """
        Clasifica un mensaje usando un system prompt personalizado.
        Permite inyectar pautas de aprendizaje.
        Sin historial (retrocompatible con tests existentes).

        Args:
            system_prompt: System prompt a usar (puede incluir pautas).
            mensaje: Texto del cliente desde WhatsApp.

        Returns:
            Diccionario con la clasificacion.
        """
        raw_response = self.client.generate(system_prompt, mensaje)
        result = parse_json_response(raw_response)

        return self._normalize_result(result)

    def classify_with_history(
        self,
        mensaje: str,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> dict:
        """
        Clasifica un mensaje usando salida estructurada (JSON Schema) e historial
        de conversacion real. El LLM resuelve el contexto ("y en talla 40?",
        "cuantas unidades?") usando el historial, no heuristicas de keywords.

        Usa generate_structured() con el schema de PlannerOutput y reintentos
        automaticos si el JSON no valida.

        Args:
            mensaje: Texto del cliente desde WhatsApp.
            history: Lista de mensajes previos de la conversacion.
                     Cada elemento debe tener "role" y "content".
            system_prompt: System prompt personalizado (puede incluir pautas).
                           Si es None, usa self.system_prompt.

        Returns:
            Diccionario con la clasificacion.
        """
        prompt = system_prompt or self.system_prompt
        options = {"num_predict": OLLAMA_NUM_PREDICT_PLANNER}

        result = self.client.generate_structured(
            system_prompt=prompt,
            user_message=mensaje,
            schema=self.schema,
            history=history,
            options=options,
        )

        return self._normalize_result(result)

    def _normalize_result(self, result: dict) -> dict:
        """
        Normaliza el resultado del LLM: valida accion, mapea talla_o_variante a talla
        para retrocompatibilidad, y asegura que los booleanos tengan valor.
        """
        valid_actions = {"consultar_stock", "pedir_aclaracion", "no_relacionado", "consultar_catalogo"}
        accion = result.get("accion", "no_relacionado")

        if accion not in valid_actions:
            accion = "no_relacionado"

        # Mapear talla a talla_o_variante para retrocompatibilidad
        talla = result.get("talla") or result.get("talla_o_variante")

        return {
            "accion": accion,
            "producto": result.get("producto"),
            "marca": result.get("marca"),
            "talla": talla,
            "talla_o_variante": talla,  # Retrocompatibilidad
            "color": result.get("color"),
            "modelo": result.get("modelo"),
            "material": result.get("material"),
            "genero": result.get("genero"),
            "cantidad_solicitada": result.get("cantidad_solicitada"),
            "precio_consultado": result.get("precio_consultado", False),
            "consultar_variantes": result.get("consultar_variantes", False),
            "atributo_faltante": result.get("atributo_faltante"),
            "mensaje_aclaracion": result.get("mensaje_aclaracion"),
        }