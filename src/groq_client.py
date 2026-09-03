"""
Cliente para Groq (LLM en la nube, gratis, rapido).
Misma interfaz publica que OllamaClient (generate, generate_structured)
para que Planner y Responder no necesiten cambios.
"""

import json
import logging

import jsonschema
from groq import Groq

from .config import GROQ_API_KEY, GROQ_MODEL
from .ollama_client import parse_json_response

logger = logging.getLogger(__name__)


class GroqLLMClient:
    """
    Cliente para Groq. Implementa la misma interfaz que OllamaClient
    para ser intercambiable dentro del Pipeline.
    """

    def __init__(self, model: str = GROQ_MODEL, api_key: str = GROQ_API_KEY):
        self.model = model
        self._client = Groq(api_key=api_key, timeout=20.0, max_retries=2)

    def _build_messages(self, system_prompt, user_message, history=None):
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", msg.get("msg", ""))
                if content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _max_tokens_de(self, options: dict | None):
        """Traduce 'num_predict' (convencion de Ollama que ya usan Planner y
        Responder) a 'max_tokens' de Groq, para no perder el control de
        longitud de respuesta al cambiar de proveedor."""
        if not options:
            return None
        return options.get("num_predict") or options.get("max_tokens")

    def generate(self, system_prompt, user_message, history=None, options=None):
        messages = self._build_messages(system_prompt, user_message, history)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=self._max_tokens_de(options),
        )
        contenido = response.choices[0].message.content
        return (contenido or "").strip()

    def generate_structured(self, system_prompt, user_message, schema, history=None, options=None, max_retries=2):
        """
        Genera JSON estructurado y lo valida contra 'schema' (jsonschema).
        Si no valida, reintenta hasta max_retries veces reenviando el error
        al modelo - mismo comportamiento que OllamaClient.generate_structured,
        para no perder la garantia anti-alucinacion al cambiar de proveedor.
        """
        messages = self._build_messages(system_prompt, user_message, history)
        max_tokens = self._max_tokens_de(options)
        last_error = None
        raw = None

        for intento in range(1, max_retries + 1):
            if intento > 1 and last_error:
                messages.append({"role": "assistant", "content": json.dumps({"error": last_error})})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Tu respuesta anterior no valido contra el schema. "
                        f"Error: {last_error}. "
                        f"Por favor responde de nuevo con un JSON valido que cumpla el schema."
                    ),
                })

            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content

            try:
                result = json.loads(raw) if raw else parse_json_response(raw or "")
            except (json.JSONDecodeError, ValueError) as e:
                last_error = f"JSON invalido: {e}"
                logger.warning("Groq devolvio JSON invalido (intento %d/%d): %s", intento, max_retries, last_error)
                continue

            try:
                jsonschema.validate(instance=result, schema=schema)
                return result
            except jsonschema.ValidationError as ve:
                last_error = str(ve)
                logger.warning("Groq no cumplio el schema (intento %d/%d): %s", intento, max_retries, last_error)
                continue

        # Todos los intentos fallaron: ultimo esfuerzo con el parser manual,
        # sin validar contra el schema (igual que hace OllamaClient).
        try:
            return parse_json_response(raw or "")
        except Exception:
            raise ValueError(
                f"Groq no genero un JSON valido tras {max_retries} intentos. "
                f"Ultimo error: {last_error}"
            )