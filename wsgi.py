"""
Punto de entrada WSGI para servidores de produccion (gunicorn).

NO ejecutar este archivo directamente con 'python wsgi.py' - no hace nada
por si solo. Debe ser cargado por un servidor WSGI externo, que importa el
objeto 'app'.

Uso en el VPS (Linux):
    gunicorn -w 1 --threads 4 -t 30 -b 0.0.0.0:5000 wsgi:app

IMPORTANTE - un solo worker (-w 1): SessionStore (src/session_store.py)
mantiene el contexto conversacional por numero de WhatsApp en memoria del
PROCESO, no compartida entre procesos. Con mas de un worker, gunicorn
reparte requests entre procesos sin afinidad por cliente, y un mismo
numero podria perder su contexto de forma intermitente al caer en un
worker distinto al de su mensaje anterior. --threads 4 sigue dando
concurrencia de I/O dentro de ese unico proceso (peticiones simultaneas
de distintos clientes), sin ese riesgo. Si el volumen de trafico exige
mas de un worker, primero hay que migrar SessionStore a un backend
compartido entre procesos (la interfaz ya esta preparada para eso, ver
docstring de session_store.py) antes de subir -w por encima de 1.

Nota: gunicorn no funciona en Windows. Para desarrollo local segui usando
'py main.py server' (servidor de desarrollo de Flask), que no cambia.
"""

from src import database as db
from src.api import app

# gunicorn importa este modulo una sola vez al arrancar cada worker; el
# bloque "if __name__" de api.py / main.py nunca se ejecuta en ese flujo,
# asi que la inicializacion de la BD debe hacerse aqui explicitamente.
db.init_db()
db.seed_from_json()