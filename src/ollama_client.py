"""
Cliente unificado para Ollama.
Proporciona una interfaz simple para generar respuestas desde modelos LLM locales.
Soporta salida estructurada (JSON Schema), historial de conversacion y reintentos.
"""

import json
import ollama

from .config import (
    OLLAMA_MODEL,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT,
    OLLAMA_TEMPERATURE,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX,
)


class OllamaClient:
    """
    Cliente para interactuar con Ollama.
    Encapsula la logica de conexion, generacion de texto y salida estructurada.
    """

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        timeout: int = OLLAMA_TIMEOUT,
        temperature: float = OLLAMA_TEMPERATURE,
    ):
        self.model = model
        self.host = host
        self.timeout = timeout
        self.temperature = temperature
        self._client = ollama.Client(host=host, timeout=timeout)

    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict] | None = None,
    ) -> list[dict]:
        """
        Construye la lista de mensajes para enviar a Ollama.

        Args:
            system_prompt: Instrucciones del sistema.
            user_message: Mensaje del usuario actual.
            history: Lista opcional de mensajes previos de la conversacion.
                     Cada elemento debe tener "role" y "content".

        Returns:
            Lista de mensajes con formato: [{"role": "system", ...}, ...history, {"role": "user", ...}]
        """
        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", msg.get("msg", ""))
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_options(self, options: dict | None = None) -> dict:
        """
        Construye el diccionario de options para Ollama.
        Mergea los defaults (temperature, keep_alive, num_ctx) con los options del caller.
        """
        default_options = {
            "temperature": self.temperature,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "num_ctx": OLLAMA_NUM_CTX,
        }
        if options:
            default_options.update(options)
        return default_options

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict] | None = None,
        options: dict | None = None,
    ) -> str:
        """
        Genera una respuesta del LLM dados un system prompt, un mensaje de usuario,
        y opcionalmente un historial de conversacion.

        Args:
            system_prompt: Instrucciones del sistema que definen el comportamiento.
            user_message: Mensaje del usuario a procesar.
            history: Lista opcional de mensajes previos (role + content).
            options: Opciones adicionales para Ollama (num_predict, etc.).

        Returns:
            Texto generado por el modelo.

        Raises:
            ConnectionError: Si no se puede conectar a Ollama.
            ValueError: Si el modelo no esta disponible.
        """
        messages = self._build_messages(system_prompt, user_message, history)
        opts = self._build_options(options)

        try:
            response = self._client.chat(
                model=self.model,
                messages=messages,
                options=opts,
            )
            return response["message"]["content"].strip()
        except Exception as e:
            error_msg = str(e).lower()
            if "connection refused" in error_msg or "connect" in error_msg:
                raise ConnectionError(
                    f"No se pudo conectar a Ollama en {self.host}. "
                    f"Verifica que Ollama este corriendo."
                ) from e
            if "not found" in error_msg or "model" in error_msg:
                raise ValueError(
                    f"El modelo '{self.model}' no esta disponible. "
                    f"Ejecuta: ollama pull {self.model}"
                ) from e
            raise

    def generate_structured(
        self,
        system_prompt: str,
        user_message: str,
        schema: dict,
        history: list[dict] | None = None,
        options: dict | None = None,
        max_retries: int = 2,
    ) -> dict:
        """
        Genera una respuesta estructurada (JSON) del LLM usando el parametro
        `format` de Ollama con un JSON Schema.

        Si el JSON no valida contra el schema, reintenta (maximo max_retries veces)
        reenviando el error al modelo antes de caer al fallback de parseo manual.

        Args:
            system_prompt: Instrucciones del sistema.
            user_message: Mensaje del usuario a procesar.
            schema: JSON Schema dict que define la estructura esperada.
            history: Lista opcional de mensajes previos.
            options: Opciones adicionales para Ollama.
            max_retries: Numero maximo de intentos (default: 2).

        Returns:
            Diccionario parseado y validado contra el schema.

        Raises:
            ConnectionError: Si no se puede conectar a Ollama.
            ValueError: Si el modelo no esta disponible o si tras max_retries
                        el JSON no valida.
        """
        import jsonschema

        messages = self._build_messages(system_prompt, user_message, history)
        opts = self._build_options(options)

        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                # En el segundo intento, agregar el error del intento anterior
                if attempt > 1 and last_error:
                    messages.append({
                        "role": "assistant",
                        "content": json.dumps({"error": last_error}),
                    })
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Tu respuesta anterior no valido contra el schema. "
                            f"Error: {last_error}. "
                            f"Por favor responde de nuevo con un JSON valido que cumpla el schema."
                        ),
                    })

                response = self._client.chat(
                    model=self.model,
                    messages=messages,
                    options=opts,
                    format=schema,
                )
                raw_content = response["message"]["content"].strip()

                # Parsear el JSON
                try:
                    result = json.loads(raw_content)
                except json.JSONDecodeError:
                    # Intentar con el parser manual como fallback
                    result = parse_json_response(raw_content)

                # Validar contra el schema
                try:
                    jsonschema.validate(instance=result, schema=schema)
                    return result
                except jsonschema.ValidationError as ve:
                    last_error = str(ve)
                    continue

            except ConnectionError:
                raise
            except ValueError:
                raise
            except Exception as e:
                error_msg = str(e).lower()
                if "connection refused" in error_msg or "connect" in error_msg:
                    raise ConnectionError(
                        f"No se pudo conectar a Ollama en {self.host}. "
                        f"Verifica que Ollama este corriendo."
                    ) from e
                if "not found" in error_msg or "model" in error_msg:
                    raise ValueError(
                        f"El modelo '{self.model}' no esta disponible. "
                        f"Ejecuta: ollama pull {self.model}"
                    ) from e
                last_error = str(e)
                continue

        # Si llegamos aqui, todos los intentos fallaron
        # Ultimo intento: usar el parser manual como fallback final
        try:
            return parse_json_response(raw_content)
        except Exception:
            raise ValueError(
                f"No se pudo generar un JSON valido tras {max_retries} intentos. "
                f"Ultimo error: {last_error}"
            )


def parse_json_response(raw_response: str) -> dict:
    """
    Extrae un JSON de la respuesta cruda del LLM.
    Soporta respuestas que vienen envueltas en markdown (```json ... ```)
    o con texto alrededor del JSON.

    Args:
        raw_response: Respuesta cruda del LLM.

    Returns:
        Diccionario parseado del JSON.

    Raises:
        ValueError: Si no se puede extraer un JSON valido.
    """
    text = raw_response.strip()

    # Intentar extraer de bloque markdown ```json ... ```
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + len("```")
        end = text.index("```", start)
        text = text[start:end].strip()

    # Buscar el primer { y el ultimo }
    brace_start = text.find("{")
    brace_end = text.rfind("}")

    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        text = text[brace_start : brace_end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"No se pudo parsear el JSON de la respuesta del LLM. "
            f"Respuesta cruda: {raw_response[:200]}..."
        ) from e