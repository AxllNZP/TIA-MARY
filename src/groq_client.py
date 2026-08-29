"""
Cliente para Groq (LLM en la nube, gratis, rapido).
Misma interfaz publica que OllamaClient (generate, generate_structured)
para que Planner y Responder no necesiten cambios.
"""

import json

from groq import Groq

from .config import GROQ_API_KEY, GROQ_MODEL


class GroqLLMClient:
    """
    Cliente para Groq. Implementa la misma interfaz que OllamaClient
    para ser intercambiable dentro del Pipeline.
    """

    def __init__(self, model: str = GROQ_MODEL, api_key: str = GROQ_API_KEY):
        self.model = model
        self._client = Groq(api_key=api_key)

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

    def generate(self, system_prompt, user_message, history=None, options=None):
        messages = self._build_messages(system_prompt, user_message, history)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()

    def generate_structured(self, system_prompt, user_message, schema, history=None, options=None, max_retries=2):
        messages = self._build_messages(system_prompt, user_message, history)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        return json.loads(raw)