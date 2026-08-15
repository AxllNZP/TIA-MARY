"""
Modulo Respondedor: Generador de respuestas para WhatsApp.
Redacta la respuesta final para el cliente usando el resultado de la consulta de inventario.
Soporta historial de conversacion para mantener coherencia contextual.
Solo usa datos del JSON recibido — NO inventa informacion.
"""

import json
import os
from pathlib import Path
from typing import Optional

from .config import NOMBRE_TIENDA, PROMPT_DIR, RESPONDER_PROMPT_FILE, OLLAMA_NUM_PREDICT_RESPONDER
from .ollama_client import OllamaClient


# Prompt por defecto del respondedor
RESPONDER_SYSTEM_PROMPT_TEMPLATE = """Eres el asistente de atencion al cliente por WhatsApp de {nombre_tienda}.
Tu tarea es redactar la respuesta final para el cliente, usando EXCLUSIVAMENTE el resultado de la consulta de inventario que te entrega el sistema.

Recibiras un JSON de entrada con esta forma:
{{
  "mensaje_cliente": "string",
  "producto_buscado": "string",
  "resultado_inventario": {{
    "encontrado": true | false,
    "cantidad_disponible": number | null,
    "precio": number | null,
    "variantes_disponibles": ["string", ...] | null
  }}
}}

Reglas para tu respuesta:
1. Responde en espanol, con un tono calido, cercano y breve (2-4 lineas maximo), como lo haria una tienda pequena atendiendo por WhatsApp.
2. Si "encontrado" es true y hay stock (cantidad_disponible > 0), confirma que si hay disponibilidad. Puedes mencionar la cantidad solo si aporta valor (ej. "nos quedan pocas unidades").
3. Si "encontrado" es true pero cantidad_disponible es 0, indica que por el momento no hay stock de ese producto especifico.
4. Si hay "variantes_disponibles" (otras tallas, colores o marcas similares), ofrecelas como alternativa de forma natural.
5. Si "encontrado" es false, indica amablemente que no manejan ese producto, sin inventar alternativas que no esten en el JSON.
6. Nunca reveles informacion tecnica (JSON, nombres de campos, que eres una IA que "consulto una base de datos"). Debe sentirse como una respuesta humana de la tienda.
7. No agregues despedidas largas ni relleno innecesario; ve directo a responder la consulta.
8. NO INVENTES datos de stock que no esten en el JSON recibido. Si el JSON no tiene un dato, no lo menciones.
9. Siempre menciona el nombre de la tienda: {nombre_tienda}.
10. Si el cliente pregunta por cantidad o unidades, menciona el numero exacto de cantidad_disponible del JSON.
11. Si el cliente pregunta por precio, menciona el precio del campo "precio" del JSON. Si el precio es null, di que no tienes el precio en este momento.
12. Si el inventario no contiene el atributo solicitado (ej: color blanco), responde explicitamente que no existe y ofrece unicamente las variantes disponibles del JSON.
13. NO infieras, NO completes, NO inventes datos que no esten en el JSON.

Ejemplos de respuestas:

Entrada: {{"mensaje_cliente":"Tienen zapatillas Nike talla 42?","producto_buscado":"zapatillas Nike","resultado_inventario":{{"encontrado":true,"cantidad_disponible":3,"precio":250.00,"variantes_disponibles":null}}}}
Respuesta: "Hola! Si, en {nombre_tienda} tenemos zapatillas Nike talla 42 disponibles. Nos quedan 3 unidades a S/ 250.00. Te las separo?"

Entrada: {{"mensaje_cliente":"cuantas unidades quedan?","producto_buscado":"zapatillas Nike talla 42","resultado_inventario":{{"encontrado":true,"cantidad_disponible":3,"precio":250.00,"variantes_disponibles":null}}}}
Respuesta: "Nos quedan 3 unidades de las zapatillas Nike talla 42 en {nombre_tienda}. Quieres que te las separe?"

Entrada: {{"mensaje_cliente":"cuanto cuesta?","producto_buscado":"zapatillas Nike talla 42","resultado_inventario":{{"encontrado":true,"cantidad_disponible":3,"precio":250.00,"variantes_disponibles":null}}}}
Respuesta: "Las zapatillas Nike talla 42 estan a S/ 250.00 en {nombre_tienda}. Te interesa?"

Entrada: {{"mensaje_cliente":"y en blanco?","producto_buscado":"zapatillas Nike talla 42","resultado_inventario":{{"encontrado":false,"cantidad_disponible":null,"precio":null,"variantes_disponibles":["Nike - talla 40 - color negro","Nike - talla 42 - color negro"]}}}}
Respuesta: "No tenemos zapatillas Nike talla 42 en color blanco en {nombre_tienda}. Solo tenemos en color negro, en tallas 40 y 42. Te interesa alguna?"

Entrada: {{"mensaje_cliente":"y de otra talla?","producto_buscado":"zapatillas Nike","resultado_inventario":{{"encontrado":true,"cantidad_disponible":8,"precio":250.00,"variantes_disponibles":["Nike - talla 40 - color negro","Nike - talla 42 - color negro"]}}}}
Respuesta: "En {nombre_tienda} tenemos zapatillas Nike en talla 40 y 42, ambas en color negro. Cual te interesa?"

Entrada: {{"mensaje_cliente":"Venden laptops?","producto_buscado":"laptops","resultado_inventario":{{"encontrado":false,"cantidad_disponible":null,"precio":null,"variantes_disponibles":null}}}}
Respuesta: "Hola! En {nombre_tienda} nos especializamos en ropa, calzado y accesorios. No manejamos laptops. Puedo ayudarte con zapatillas, polos, jeans, medias, gorras o casacas. Que buscas?"
"""


class Responder:
    """
    Generador de respuestas para el cliente de WhatsApp.
    Usa Ollama para redactar respuestas naturales a partir de resultados de inventario.
    Soporta historial de conversacion para mantener coherencia contextual.
    Solo usa datos del JSON recibido — NO inventa informacion.
    """

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        nombre_tienda: str = NOMBRE_TIENDA,
    ):
        """
        Args:
            client: Cliente de Ollama. Si no se provee, se crea uno con defaults.
            nombre_tienda: Nombre de la tienda para personalizar las respuestas.
        """
        self.client = client or OllamaClient()
        self.nombre_tienda = nombre_tienda
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo o usa el prompt por defecto."""
        prompt_path = Path(PROMPT_DIR) / RESPONDER_PROMPT_FILE
        if prompt_path.exists():
            template = prompt_path.read_text(encoding="utf-8")
            return template.replace("{nombre_tienda}", self.nombre_tienda)
        return RESPONDER_SYSTEM_PROMPT_TEMPLATE.format(nombre_tienda=self.nombre_tienda)

    def generate_response(
        self,
        mensaje_cliente: str,
        producto_buscado: str,
        resultado_inventario: dict,
    ) -> str:
        """
        Genera una respuesta para el cliente basada en el resultado del inventario.
        Usa el system prompt por defecto. Sin historial (retrocompatible).

        Args:
            mensaje_cliente: Mensaje original del cliente.
            producto_buscado: Producto que el cliente esta buscando.
            resultado_inventario: Resultado de la consulta de inventario.

        Returns:
            Texto de respuesta listo para enviar por WhatsApp.
        """
        return self.generate_response_with_prompt(
            self.system_prompt, mensaje_cliente, producto_buscado, resultado_inventario
        )

    def generate_response_with_prompt(
        self,
        system_prompt: str,
        mensaje_cliente: str,
        producto_buscado: str,
        resultado_inventario: dict,
    ) -> str:
        """
        Genera una respuesta usando un system prompt personalizado.
        Permite inyectar pautas de aprendizaje. Sin historial (retrocompatible).

        Args:
            system_prompt: System prompt a usar (puede incluir pautas).
            mensaje_cliente: Mensaje original del cliente.
            producto_buscado: Producto que el cliente esta buscando.
            resultado_inventario: Resultado de la consulta de inventario.

        Returns:
            Texto de respuesta listo para enviar por WhatsApp.

        Raises:
            ValueError: Si el resultado_inventario no tiene el formato esperado.
        """
        # Validar estructura del resultado de inventario
        if "encontrado" not in resultado_inventario:
            raise ValueError(
                "resultado_inventario debe contener el campo 'encontrado'"
            )

        # Construir el mensaje para el LLM — incluye precio
        input_data = self._build_input_data(
            mensaje_cliente, producto_buscado, resultado_inventario
        )

        user_message = json.dumps(input_data, ensure_ascii=False)
        respuesta = self.client.generate(system_prompt, user_message)
        return respuesta.strip()

    def generate_response_with_history(
        self,
        system_prompt: str,
        mensaje_cliente: str,
        producto_buscado: str,
        resultado_inventario: dict,
        history: list[dict] | None = None,
    ) -> str:
        """
        Genera una respuesta usando un system prompt personalizado e historial
        de conversacion real. El LLM mantiene coherencia contextual usando
        los mensajes previos.

        Args:
            system_prompt: System prompt a usar (puede incluir pautas).
            mensaje_cliente: Mensaje original del cliente.
            producto_buscado: Producto que el cliente esta buscando.
            resultado_inventario: Resultado de la consulta de inventario.
            history: Lista de mensajes previos de la conversacion.

        Returns:
            Texto de respuesta listo para enviar por WhatsApp.

        Raises:
            ValueError: Si el resultado_inventario no tiene el formato esperado.
        """
        # Validar estructura del resultado de inventario
        if "encontrado" not in resultado_inventario:
            raise ValueError(
                "resultado_inventario debe contener el campo 'encontrado'"
            )

        # Construir el mensaje para el LLM — incluye precio
        input_data = self._build_input_data(
            mensaje_cliente, producto_buscado, resultado_inventario
        )

        user_message = json.dumps(input_data, ensure_ascii=False)
        options = {"num_predict": OLLAMA_NUM_PREDICT_RESPONDER}

        respuesta = self.client.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
            options=options,
        )
        return respuesta.strip()

    def _build_input_data(
        self,
        mensaje_cliente: str,
        producto_buscado: str,
        resultado_inventario: dict,
    ) -> dict:
        """
        Construye el JSON que se envia al LLM.
        Incluye el precio del inventario (Problema 3: antes no se enviaba).
        """
        precio = resultado_inventario.get("precio")
        if precio is None:
            precio = resultado_inventario.get("_precio")

        return {
            "mensaje_cliente": mensaje_cliente,
            "producto_buscado": producto_buscado,
            "resultado_inventario": {
                "encontrado": resultado_inventario.get("encontrado"),
                "cantidad_disponible": resultado_inventario.get("cantidad_disponible"),
                "precio": precio,
                "variantes_disponibles": resultado_inventario.get(
                    "variantes_disponibles"
                ),
            },
        }