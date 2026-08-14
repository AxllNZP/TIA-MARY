# Configuración del asistente de WhatsApp para TÍA MARY

# Nombre de la tienda (usado en las respuestas)
NOMBRE_TIENDA = "TÍA MARY"

# Configuracion de Ollama
OLLAMA_MODEL = "llama3.1:8b"  # Modelo 8B con mejor seguimiento de schema
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_TIMEOUT = 60  # segundos
OLLAMA_TEMPERATURE = 0.1  # Baja temperatura para respuestas deterministas
OLLAMA_KEEP_ALIVE = "30m"  # Mantiene el modelo cargado 30 min tras inactividad
OLLAMA_NUM_PREDICT_PLANNER = 200  # Max tokens de salida para el Planner
OLLAMA_NUM_PREDICT_RESPONDER = 150  # Max tokens de salida para el Responder
OLLAMA_NUM_CTX = 2048  # Tamano del contexto (tokens de entrada)

# Archivos de prompts
PROMPT_DIR = "prompts"
PLANNER_PROMPT_FILE = "planner_prompt.txt"
RESPONDER_PROMPT_FILE = "responder_prompt.txt"

# Base de datos
DATABASE_PATH = "data/tienda.db"
SEED_DATA_PATH = "data/seed_productos.json"

# Historial de aprendizaje
FEEDBACK_PATH = "data/feedback.jsonl"

import os

# Servidor Flask
# Host seguro por defecto (solo localhost). Para exponer en LAN/red publica,
# debe declararse explicitamente: FLASK_HOST=0.0.0.0
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = 5000
# DEBUG solo se activa si se declara explicitamente (ej. desarrollo local).
# Por defecto, desactivado -> evita exponer el debugger de Werkzeug.
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
