# TÍA MARY — Asistente de WhatsApp con IA

Asistente virtual para tienda minorista que responde consultas de stock por WhatsApp usando IA. El sistema clasifica la intención del cliente, consulta una base de datos SQLite real y redacta respuestas naturales en español.

Soporta dos proveedores de LLM intercambiables (mismo comportamiento, misma calidad de respuesta):

| Proveedor | Dónde corre | Costo | Requisito |
|---|---|---|---|
| **Ollama** | Local, en tu PC | Sin costo de API | Instalar Ollama + descargar el modelo (~4.7 GB) |
| **Groq** | En la nube | Gratis dentro de límites generosos | Solo una API key |

Elige el que prefieras — el resto del sistema (Planner, Inventario, Responder) funciona idéntico con cualquiera de los dos.

---

## Arquitectura del Pipeline

```
Mensaje WhatsApp
       |
       v
┌─────────────────┐
│  1. PLANNER     │  Clasifica la intencion: consultar_stock,
│  (Ollama/Groq)  │  pedir_aclaracion, no_relacionado, consultar_catalogo.
│                 │  Extrae: producto, marca, talla, color, precio_consultado...
└────────┬────────┘
         | JSON validado contra schema
         v
┌─────────────────┐
│  2. INVENTARIO  │  Consulta SQLite real con 20 productos
│  (SQLite)       │  (zapatillas, polos, jeans, medias, etc.)
└────────┬────────┘
         | JSON: {encontrado, cantidad_disponible, variantes...}
         v
┌─────────────────┐
│  3. RESPONDER   │  Redacta respuesta natural, calida y breve.
│  (Ollama/Groq)  │  Menciona TIA MARY, ofrece variantes si hay.
└────────┬────────┘
         |
         v
   Respuesta WhatsApp
```

El contexto de cada conversación (producto, marca, talla, historial) se aísla por `session_id` en memoria (`SessionStore`), con expiración automática de sesiones inactivas — cada número de WhatsApp mantiene su propio hilo de conversación sin mezclarse con otros clientes.

### Pautas de Aprendizaje

Las pautas se inyectan automáticamente en los prompts del Planner y Responder **en cada consulta**, permitiendo mejora continua sin reiniciar el sistema.

---

## Requisitos

| Componente | Versión | Descripción |
|---|---|---|
| Python | 3.10+ | Probado con 3.14 |
| Ollama **o** Groq | — | Ver tabla de arriba; solo necesitas uno de los dos |

---

## Instalación

### 1. Clonar o copiar el proyecto

```bash
cd "C:\Users\AXELL\Desktop\TIA MARY"
```

### 2. Instalar dependencias Python

```bash
pip install -r requirements.txt
```

### 3. Elegir e instalar tu proveedor de LLM

**Opción A — Ollama (local):**

Descarga Ollama desde https://ollama.com/download e instala. Luego descarga el modelo:

```bash
ollama pull llama3.1:8b
```

Ollama debe estar corriendo en segundo plano (normalmente se inicia solo al instalar). Verifica con `ollama list` — debe aparecer `llama3.1:8b`.

**Opción B — Groq (nube):**

Crea una cuenta gratis en [console.groq.com](https://console.groq.com), genera una API key, y guárdala — la necesitas en el paso 4.

### 4. Configurar las variables de entorno

Este es el paso más importante y el que más dudas suele generar — va con su propia sección abajo: **[Guía de variables de entorno](#guía-de-variables-de-entorno)**.

### 5. Inicializar la base de datos

```bash
py main.py initdb
```

Esto crea `data/tienda.db` y carga 20 productos de prueba desde `data/seed_productos.json`.

---

## Guía de variables de entorno

El proyecto no funciona con valores por defecto para nada relacionado a seguridad — es intencional (*fail-closed*: si falta un secreto, el sistema rechaza en vez de dejar pasar). Necesitas configurar estas variables **antes** de arrancar el servidor.

### Variables obligatorias

| Variable | Para qué sirve | Cómo obtenerla |
|---|---|---|
| `FLASK_SECRET_KEY` | Firma las cookies de sesión del panel admin | Generarla tú (ver abajo) |
| `ADMIN_PASSWORD_HASH` | Contraseña del panel `/admin` (nunca en texto plano) | Generarla tú (ver abajo) |
| `ADMIN_API_TOKEN` | Protege `/api/pautas`, `/api/feedback`, `/api/stats`, `/api/contexto-mejora` | Inventar cualquier string largo y aleatorio |
| `WEBHOOK_SECRET` | Protege el webhook simulado `/api/webhook` | Inventar cualquier string largo y aleatorio |
| `LLM_PROVIDER` | `ollama` o `groq` — cuál usar | Tú decides |
| `ENTORNO` | `desarrollo` habilita los webhooks de prueba; sin esto, quedan en 404 | `desarrollo` mientras pruebas localmente |

### Variables condicionales

| Variable | Cuándo la necesitas |
|---|---|
| `GROQ_API_KEY` | Solo si `LLM_PROVIDER=groq` |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | Solo si vas a conectar un número real de Meta Cloud API — no se necesitan para probar localmente con el chat de prueba o el webhook simulado |

### Generar `ADMIN_PASSWORD_HASH`

Elige la contraseña que vas a usar para entrar a `/admin` y corre:

```bash
py -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('TU_CONTRASEÑA_AQUI'))"
```

Copia el resultado completo (empieza con `scrypt:...`) — ese es el valor de `ADMIN_PASSWORD_HASH`. La contraseña en texto plano no se guarda en ningún lado; solo el hash.

### Generar `FLASK_SECRET_KEY` y demás secretos aleatorios

```bash
py -c "import secrets; print(secrets.token_hex(32))"
```

Corre este comando por separado para cada uno de: `FLASK_SECRET_KEY`, `ADMIN_API_TOKEN`, `WEBHOOK_SECRET`. Usa un valor **distinto** para cada variable — no reutilices el mismo string en varias.

### Cómo setear las variables (Windows `cmd.exe`)

**Opción temporal (solo dura mientras esa ventana esté abierta):**

```cmd
set FLASK_SECRET_KEY=el_valor_que_generaste
set ADMIN_PASSWORD_HASH=el_hash_que_generaste
set ADMIN_API_TOKEN=otro_valor_aleatorio
set WEBHOOK_SECRET=otro_valor_aleatorio_distinto
set LLM_PROVIDER=groq
set GROQ_API_KEY=tu_api_key_de_groq
set ENTORNO=desarrollo
```

Corre estos comandos **en la misma ventana** donde después vas a ejecutar `py main.py server` — si abres una ventana nueva, hay que setearlas de nuevo.

**Opción persistente (sobrevive a cerrar la ventana, usando `setx`):**

```cmd
setx FLASK_SECRET_KEY "el_valor_que_generaste"
```

Repite por cada variable. `setx` las guarda en el registro de Windows para tu usuario — solo necesitas correrlo una vez, pero **tienes que abrir una ventana nueva de `cmd`** para que la variable esté disponible (no aplica a la ventana donde corriste `setx`). Ten en cuenta que quedan guardadas de forma más permanente en tu sistema; si compartes la PC, considera la opción temporal en su lugar.

### Verificar que una variable quedó bien seteada

```cmd
echo %ADMIN_PASSWORD_HASH%
```

Si te devuelve el valor esperado, está bien. Si te devuelve vacío o literalmente `%ADMIN_PASSWORD_HASH%`, no se seteó en esa sesión de shell.

---

## Ejecución

### Modo Demo (consola interactiva)

```bash
py main.py
```

Escribe mensajes como si fueras un cliente y recibe respuestas inmediatas. Ejemplos:
- `"Tienen zapatillas Nike talla 42?"`
- `"Busco un polo azul talla M"`
- `"Venden laptops?"`
- `"stats"` (muestra estadísticas)

### Modo Servidor (API + Panel Web)

```bash
py main.py server
```

Inicia Flask en `http://127.0.0.1:5000` (por defecto solo accesible desde tu propia PC — ver nota de `FLASK_HOST` más abajo). Inicializa la base de datos automáticamente si no existe.

### Panel de administración (`/admin`)

Entra a `http://localhost:5000/admin` — te va a redirigir a `/admin/login`. Ingresa la contraseña que elegiste al generar `ADMIN_PASSWORD_HASH`. Desde el panel puedes:

- Ver el historial de consultas y calificar respuestas (👍/👎)
- Agregar pautas de mejora
- Probar el bot con el "Chat de Prueba" integrado
- Cerrar sesión con el botón "Cerrar sesión" arriba a la derecha

**Seguridad del login:** 5 intentos fallidos bloquean tu IP por 5 minutos; la sesión expira sola a las 2 horas.

### Endpoints disponibles

| Endpoint | Método | Auth requerida | Descripción |
|---|---|---|---|
| `/admin` | GET | Sesión de admin | Panel de administración |
| `/admin/login` | GET, POST | — | Login del panel |
| `/admin/logout` | POST | Sesión de admin | Cierra sesión |
| `/api/chat` | POST | — | Chat de prueba (sin WhatsApp), retorna respuesta + detalles internos |
| `/api/webhook` | POST | Firma HMAC (`X-Webhook-Signature`) + `ENTORNO=desarrollo` | Webhook simulado para pruebas locales |
| `/api/webhook-twilio` | POST | `ENTORNO=desarrollo` (sin verificación de firma todavía) | Sandbox de Twilio, endpoint de prueba |
| `/api/webhook-meta` | GET | `hub.verify_token` | Verificación inicial que exige Meta al configurar el Callback URL |
| `/api/webhook-meta` | POST | Firma HMAC (`X-Hub-Signature-256`) | Webhook real de Meta Cloud API |
| `/api/feedback` | POST | `Authorization: Bearer <ADMIN_API_TOKEN>` | Registrar feedback sobre una consulta |
| `/api/pautas` | GET, POST | `Authorization: Bearer <ADMIN_API_TOKEN>` | Listar/crear pautas de mejora |
| `/api/stats` | GET | `Authorization: Bearer <ADMIN_API_TOKEN>` | Estadísticas del sistema |
| `/api/contexto-mejora` | GET | `Authorization: Bearer <ADMIN_API_TOKEN>` | Datos para análisis de mejora (incluye pautas y quejas de clientes) |

### Probar con un celular real en la misma red WiFi

1. Averigua la IP de tu PC: `ipconfig` (busca `IPv4 Address`, ej: `192.168.1.45`)
2. Setea `set FLASK_HOST=0.0.0.0` antes de arrancar el servidor (por defecto solo escucha en `127.0.0.1`, para que no quede expuesto en la red sin querer)
3. Inicia el servidor: `py main.py server`
4. Desde el celular, abre el navegador y ve a `http://192.168.1.45:5000/admin`

### Conectar un número real de WhatsApp (Meta Cloud API)

El endpoint `/api/webhook-meta` ya está implementado y probado end-to-end con tráfico real de Meta (firma HMAC verificada, envío de respuesta real vía Meta Cloud API). Requiere:

- Una app de Meta for Developers con el producto WhatsApp habilitado
- Las variables `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` configuradas
- Un túnel público hacia tu servidor local (por ejemplo `ngrok http 5000`) para pruebas mientras no tengas un dominio propio

La guía completa de despliegue con dominio propio, HTTPS y servidor de producción (`wsgi.py` + gunicorn) se documentará como parte de la fase de infraestructura, cuando se defina el plan de producción — este README cubre el uso y pruebas en tu máquina local.

---

## Seguridad implementada

Resumen de las protecciones activas, para referencia rápida:

- **Autenticación del panel admin**: contraseña con hash `scrypt`, sesión Flask firmada, expiración a las 2 horas.
- **CSRF**: token sincronizado (`synchronizer token pattern`) en `/admin/login` y `/admin/logout`.
- **Límite de intentos de login**: 5 fallos bloquean por 5 minutos, particionado por IP de origen.
- **Registro de intentos sospechosos**: logins fallidos, bloqueos e intentos de CSRF quedan en el log del servidor.
- **Webhooks verificados por firma**: `/api/webhook` (HMAC genérico) y `/api/webhook-meta` (HMAC de Meta, `X-Hub-Signature-256`) rechazan cualquier petición sin firma válida antes de procesar el cuerpo.
- **Endpoints administrativos protegidos**: `/api/pautas`, `/api/feedback`, `/api/stats`, `/api/contexto-mejora` requieren `Authorization: Bearer <ADMIN_API_TOKEN>`.
- **Fail-closed en todos los secretos**: si falta cualquier variable de seguridad, el endpoint correspondiente rechaza — nunca queda abierto por defecto.
- **Bandera de entorno**: `/api/webhook` y `/api/webhook-twilio` (endpoints de prueba) quedan deshabilitados (`404`) a menos que se configure `ENTORNO=desarrollo`.
- **Cookies de sesión endurecidas**: `HttpOnly`, `Secure`, `SameSite=Lax`.
- **Aislamiento de sesiones conversacionales**: cada número de WhatsApp tiene su propio contexto e historial, con expiración automática tras 24h de inactividad.

---

## Pruebas

### Tests rápidos (lógica, sin LLM)

```bash
py main.py test
```

11 pruebas que validan: base de datos, búsqueda de productos, registro de consultas, feedback, pautas y estadísticas.

### Suite completa de pytest

```bash
py -m pytest tests/ -v
```

129 pruebas en total, cubriendo: parser JSON, Planner, Responder, filtros de búsqueda de productos, aislamiento de sesiones, seguimiento conversacional, y toda la superficie de seguridad (login + CSRF + rate limiting, autenticación de `/api/pautas` y `/api/feedback`, firma de `/api/webhook` y `/api/webhook-meta`, configuración segura de Flask).

Las pruebas de `TestPlanner`, `TestPlannerMultiTurn`, `TestResponder`, `TestResponderMultiTurn` y las de seguimiento end-to-end requieren un LLM real corriendo (Ollama o Groq configurado) — el resto son autocontenidas.

---

## Base de Datos — 20 Productos de Ejemplo

`data/tienda.db` (SQLite) contiene:

| Categoría | Productos | Marcas | Tallas |
|---|---|---|---|
| Calzado | Zapatillas | Nike, Adidas | 38-42 |
| Ropa | Polos | Lacoste, Tommy Hilfiger | M, L |
| Ropa | Jeans | Levi's | 30-34 |
| Ropa | Casacas | North Face | M |
| Accesorios | Medias | Puma, Adidas | única |
| Accesorios | Gorras | New Era, Nike | única |

**Casos incluidos a propósito para pruebas:**
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

Desde el panel de administración (`/admin`, con login):

### 1. Ver historial completo
Todas las consultas de clientes, respuestas enviadas, si el producto fue encontrado o no.

### 2. Calificar respuestas
Cada consulta tiene un selector 👍/👎 (requiere estar autenticado en el panel).

### 3. Agregar pautas de mejora

| Tipo | Aplica a | Ejemplo |
|---|---|---|
| `planner` | Clasificador | "Cuando el cliente diga 'chompas', clasifícalo como 'casaca'" |
| `responder` | Respuestas | "Siempre menciona el precio cuando haya stock disponible" |
| `general` | Ambos | "La tienda no vende electrónicos, solo ropa y calzado" |

### 4. Monitorear estadísticas
Consultas totales, productos con/sin stock, feedback positivo/negativo, pautas activas.

---

## Estructura de Archivos

```
TIA MARY/
|-- main.py                        # Punto de entrada (demo, server, test, initdb)
|-- wsgi.py                        # Entrypoint para servidor WSGI de produccion (gunicorn, Linux)
|-- requirements.txt
|-- README.md                      # Este archivo
|
|-- prompts/
|   |-- planner_prompt.txt         # System prompt del clasificador
|   |-- responder_prompt.txt       # System prompt del respondedor
|
|-- data/
|   |-- tienda.db                  # Base de datos SQLite (autogenerada)
|   |-- seed_productos.json        # Datos semilla (20 productos)
|
|-- src/
|   |-- config.py                  # Configuracion central (variables de entorno)
|   |-- ollama_client.py           # Cliente Ollama + parser JSON
|   |-- groq_client.py             # Cliente Groq (misma interfaz que Ollama)
|   |-- database.py                # Capa de datos SQLite
|   |-- inventario.py              # Capa de negocio (consulta stock)
|   |-- planner.py                 # Modulo 1: Clasificador de intencion
|   |-- responder.py               # Modulo 2: Generador de respuestas
|   |-- pipeline.py                # Orquestador del flujo completo
|   |-- session_store.py           # Aislamiento de contexto/historial por sesion
|   |-- learning.py                # Motor de aprendizaje (pautas + feedback)
|   |-- api.py                     # API Flask + dashboard HTML + seguridad
|
|-- tests/                         # 129 pruebas (ver seccion Pruebas)
```

---

## Solución de Problemas

### "No se pudo conectar a Ollama"

Ollama no está corriendo. Inícialo manualmente con `ollama serve`, o abre la aplicación Ollama desde el menú de inicio de Windows.

### "El modelo 'llama3.1:8b' no está disponible"

```bash
ollama pull llama3.1:8b
```

### Error con Groq (401, autenticación)

Confirma que `GROQ_API_KEY` esté seteada en la misma ventana donde arrancaste el servidor (`echo %GROQ_API_KEY%`), y que `LLM_PROVIDER=groq` esté seteado también.

### El login del panel admin no funciona / dice "contraseña incorrecta" siempre

Confirma que `ADMIN_PASSWORD_HASH` esté seteado (`echo %ADMIN_PASSWORD_HASH%`) y que sea el hash generado con `generate_password_hash`, no la contraseña en texto plano.

### El panel dice "Demasiados intentos fallidos"

Espera 5 minutos, o reinicia el servidor (el contador vive en memoria y se reinicia junto con el proceso).

### `/api/webhook` o `/api/webhook-twilio` devuelven 404

Falta `set ENTORNO=desarrollo` en tu sesión de terminal — por diseño, estos endpoints de prueba quedan deshabilitados si no se configura explícitamente.

### Error de encoding/emojis en terminal

El proyecto usa solo caracteres ASCII en los prints. Si ves errores de encoding, asegúrate de usar PowerShell o Windows Terminal (no CMD tradicional).

### Puerto 5000 ocupado

A diferencia de `FLASK_HOST`, el puerto no se lee de una variable de entorno — edita directamente `src/config.py` y cambia `FLASK_PORT = 5000` por el puerto que prefieras (ej. `8080`).

---

## Licencia

Uso interno — TIA MARY.