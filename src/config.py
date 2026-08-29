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

# Limite de pautas inyectadas en el prompt (M4). El esquema de 'pautas' no
# tiene campo de prioridad/peso/expiracion, asi que se usa el orden ya
# existente (creado_en DESC) y se toman las N mas recientes. Evita que el
# prompt crezca indefinidamente y deje sin margen a mensaje/historial/
# respuesta dentro de OLLAMA_NUM_CTX. No trunca el texto de cada pauta.
MAX_PAUTAS_EN_PROMPT = 8

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


# Token de administrador para proteger endpoints sensibles (ej. /api/pautas).
# Sin valor por defecto utilizable: si no se configura, el endpoint protegido
# debe rechazar todas las solicitudes (fail-closed), nunca fail-open.
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")

# Secreto compartido para verificar la firma HMAC de /api/webhook.
# Mecanismo generico (no ligado a un proveedor especifico): el proyecto aun
# no tiene integracion real de Twilio/Meta (ver docstring de webhook() en
# api.py, que hoy "simula" el proveedor). Cuando se integre un proveedor
# definitivo, este mecanismo debe sustituirse por su verificacion nativa
# (ej. X-Twilio-Signature con HMAC-SHA1, o X-Hub-Signature-256 de Meta).
# Sin valor por defecto utilizable: fail-closed si no se configura.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

# Meta WhatsApp Cloud API (prueba de fuego, numero de prueba de Meta)
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")

# Groq (LLM en la nube, gratis, reemplaza a Ollama en produccion/pruebas reales)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # "ollama" o "groq"