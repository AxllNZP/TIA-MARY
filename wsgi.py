"""
Punto de entrada WSGI para servidores de produccion (gunicorn).

NO ejecutar este archivo directamente con 'python wsgi.py' - no hace nada
por si solo. Debe ser cargado por un servidor WSGI externo, que importa el
objeto 'app'.

Uso en el VPS (Linux):
    gunicorn -w 2 --threads 4 -t 30 -b 0.0.0.0:5000 wsgi:app

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