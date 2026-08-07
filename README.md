# TIA MARY - Asistente de WhatsApp con IA Local (Ollama)

Asistente virtual para tienda minorista que responde consultas de stock por WhatsApp usando inteligencia artificial 100% local (sin costo de API). El sistema clasifica la intencion del cliente, consulta una base de datos SQLite real y redacta respuestas naturales en español.

---

## Arquitectura del Pipeline

```
Mensaje WhatsApp
       |
       v
┌─────────────────┐
│  1. PLANNER     │  Clasifica la intencion: consultar_stock,
│  (Ollama LLM)   │  pedir_aclaracion, o no_relacionado.
│                 │  Extrae: producto, marca, talla, cantidad.
└────────┬────────┘
         | JSON: {accion, producto, marca, talla_o_variante...}
         v
┌─────────────────┐
│  2. INVENTARIO  │  Consulta SQLite real con 20 productos
│  (SQLite)       │  (zapatillas, polos, jeans, medias, etc.)
└────────┬────────┘
         | JSON: {encontrado, cantidad_disponible, variantes...}
         v
┌─────────────────┐
│  3. RESPONDER   │  Redacta respuesta natural, calida y breve.
│  (Ollama LLM)   │  Menciona TIA MARY, ofrece variantes si hay.
└────────┬────────┘
         |
         v
   Respuesta WhatsApp
```

### Pautas de Aprendizaje

Las pautas se inyectan automaticamente en los prompts del Planner y Responder **en cada consulta**, permitiendo mejora continua sin reiniciar el sistema.

---

## Requisitos

| Componente | Version | Descripcion |
|---|---|---|
| Python | 3.10+ | Probado con 3.14 |
| Ollama | v0.30+ | Motor LLM local |
| Modelo | llama3.2:3b | ~2 GB, espanol funcional |

---

## Instalacion

### 1. Clonar o copiar el proyecto

```bash
cd "C:\Users\AXELL\Desktop\TIA MARY"
```

### 2. Instalar dependencias Python

```bash
pip install -r requirements.txt
```

### 3. Instalar y ejecutar Ollama

Descargar Ollama desde https://ollama.com/download e instalar. Luego descargar el modelo:

```bash
ollama pull llama3.2:3b
```

Ollama debe estar corriendo en segundo plano (normalmente se inicia automaticamente al instalar). Verificar:

```bash
ollama list
```

Debe mostrar `llama3.2:3b` en la lista.

### 4. Inicializar la base de datos

```bash
py main.py initdb
```

Esto crea `data/tienda.db` y carga 20 productos de prueba desde `data/seed_productos.json`.

---

## Ejecucion

### Modo Demo (consola interactiva)

Prueba el pipeline completo desde la terminal:

```bash
py main.py
```

Escribe mensajes como si fueras un cliente y recibe respuestas inmediatas. Ejemplos:
- `"Tienen zapatillas Nike talla 42?"`
- `"Busco un polo azul talla M"`
- `"Venden laptops?"`
- `"stats"` (muestra estadisticas)

### Modo Servidor (API + Panel Web)

```bash
py main.py server
```

Inicia Flask en `http://0.0.0.0:5000`. Endpoints disponibles:

| Endpoint | Metodo | Descripcion |
|---|---|---|
| `/admin` | GET | Panel de administracion web |
| `/api/webhook` | POST | Webhook para WhatsApp (recibe `{"mensaje": "..."}`) |
| `/api/chat` | POST | Chat de prueba (retorna respuesta + detalles internos) |
| `/api/feedback` | POST | Registrar feedback sobre una consulta |
| `/api/pautas` | GET/POST | Listar/crear pautas de mejora |
| `/api/stats` | GET | Estadisticas del sistema |
| `/api/contexto-mejora` | GET | Datos para analisis de mejora |

### Probar con un celular real en la misma red WiFi

1. Averigua la IP de tu PC: `ipconfig` (busca `IPv4 Address`, ej: `192.168.1.45`)
2. Inicia el servidor: `py main.py server`
3. Desde el celular, abre el navegador y ve a `http://192.168.1.45:5000/admin`
4. Usa la seccion "Chat de Prueba" o envia POST a `http://192.168.1.45:5000/api/webhook`
5. Para conectar WhatsApp real: configura el webhook de Twilio/Meta/WhatsApp Business API apuntando a `/api/webhook`

---

## Pruebas

### Tests rapidos (logica, sin LLM)

```bash
py main.py test
```

11 pruebas que validan: base de datos, busqueda de productos, registro de consultas, feedback, pautas y estadisticas.

### Suite completa (con LLM)

```bash
py -m pytest tests/ -v
```

18 pruebas: 5 del parser JSON, 7 del Planner (clasificacion de intencion), 6 del Responder (generacion de respuestas).

---

## Base de Datos — 20 Productos de Ejemplo

`data/tienda.db` (SQLite) contiene:

| Categoria | Productos | Marcas | Tallas |
|---|---|---|---|
| Calzado | Zapatillas | Nike, Adidas | 38-42 |
| Ropa | Polos | Lacoste, Tommy Hilfiger | M, L |
| Ropa | Jeans | Levi's | 30-34 |
| Ropa | Casacas | North Face | M |
| Accesorios | Medias | Puma, Adidas | unica |
| Accesorios | Gorras | New Era, Nike | unica |

**Casos incluidos a proposito para pruebas:**
- Nike talla 38: **sin stock** (stock=0)
- Levi's talla 30: **sin stock** (stock=0)
- Gorra Nike: **sin stock** (stock=0)
- Laptops, tablets: **no existen** en la BD

Los datos semilla se pueden editar en `data/seed_productos.json` y recargar con:

```bash
del data\tienda.db
py main.py initdb
```

---

## Zona de Aprendizaje (Prueba y Error)

Accede al panel de administracion en `http://localhost:5000/admin` para:

### 1. Ver historial completo
Todas las consultas de clientes, respuestas enviadas, si el producto fue encontrado o no.

### 2. Calificar respuestas
Cada consulta tiene un selector 👍/👎 para marcar si la respuesta fue buena o mala. Esto alimenta las estadisticas y ayuda a identificar patrones de error.

### 3. Agregar pautas de mejora
Tres tipos de pautas que se inyectan automaticamente en los prompts:

| Tipo | Aplica a | Ejemplo |
|---|---|---|
| `planner` | Clasificador | "Cuando el cliente diga 'chompas', clasificalo como 'casaca'" |
| `responder` | Respuestas | "Siempre menciona el precio cuando haya stock disponible" |
| `general` | Ambos | "La tienda no vende electronicos, solo ropa y calzado" |

### 4. Monitorear estadisticas
Consultas totales, productos con/sin stock, feedback positivo/negativo, pautas activas.

---

## Estructura de Archivos

```
TIA MARY/
|-- main.py                    # Punto de entrada (demo, server, test, initdb)
|-- requirements.txt           # ollama, pytest, flask
|-- README.md                  # Este archivo
|
|-- prompts/
|   |-- planner_prompt.txt     # System prompt del clasificador
|   |-- responder_prompt.txt   # System prompt del respondedor
|
|-- data/
|   |-- tienda.db              # Base de datos SQLite (autogenerada)
|   |-- seed_productos.json    # Datos semilla (20 productos)
|
|-- src/
|   |-- config.py              # Configuracion central
|   |-- ollama_client.py       # Cliente Ollama + parser JSON
|   |-- database.py            # Capa de datos SQLite
|   |-- inventario.py          # Capa de negocio (consulta stock)
|   |-- planner.py             # Modulo 1: Clasificador de intencion
|   |-- responder.py           # Modulo 2: Generador de respuestas
|   |-- pipeline.py            # Orquestador del flujo completo
|   |-- learning.py            # Motor de aprendizaje (pautas + feedback)
|   |-- api.py                 # API Flask + dashboard HTML
|
|-- tests/
    |-- test_planner.py        # Tests del parser JSON + Planner (13 tests)
    |-- test_responder.py      # Tests del Responder (6 tests)
```

---

## Solucion de Problemas

### "No se pudo conectar a Ollama"

Ollama no esta corriendo. Inicialo manualmente:

```bash
ollama serve
```

O abre la aplicacion Ollama desde el menu de inicio de Windows.

### "El modelo 'llama3.2:3b' no esta disponible"

```bash
ollama pull llama3.2:3b
```

### Error de encoding/emojis en terminal

El proyecto usa solo caracteres ASCII en los prints. Si ves errores de encoding, asegurate de usar PowerShell o Windows Terminal (no CMD tradicional).

### Puerto 5000 ocupado

Edita `src/config.py` y cambia `FLASK_PORT = 5000` por otro puerto (ej: 8080).

---

## Licencia

Uso interno - TIA MARY.