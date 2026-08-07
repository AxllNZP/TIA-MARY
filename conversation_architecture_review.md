# Conversation Architecture Review — TIA MARY

## Resumen Ejecutivo

Se analizaron 9 archivos del sistema conversacional de TIA MARY. Se detectaron **11 problemas de arquitectura conversacional** que causan perdida de contexto, atributos faltantes y alucinaciones del Response Generator.

---

## Problemas Detectados

### PROBLEMA 1: Schema del Planner no tiene campo `color`

| Campo | Valor |
|---|---|
| **Archivo** | `src/planner.py` |
| **Funcion** | `PlannerOutput` (lineas 56-83) |
| **Causa** | El schema Pydantic tiene `talla_o_variante` pero NO tiene un campo `color` separado. Cuando el usuario dice "y en blanco?", el LLM no tiene donde poner el color. Lo mete en `talla_o_variante` o lo pierde. |
| **Impacto** | Perdida del atributo color en preguntas de seguimiento como "y en blanco?", "solo negro?", "lo tienen en rojo?" |
| **Prioridad** | ALTA |
| **Soluciones** | 1. Agregar `color: Optional[str]` al modelo `PlannerOutput`. 2. Actualizar el prompt con ejemplos de extraccion de color. 3. Actualizar `inventario.py` para pasar el color a la BD. |

### PROBLEMA 2: `inventario.py` ignora el color completamente

| Campo | Valor |
|---|---|
| **Archivo** | `src/inventario.py` |
| **Funcion** | `consultar_stock()` (linea 130) |
| **Causa** | `color=None` hardcoded — nunca pasa el color del plan a la BD. Incluso si el Planner extrajera el color, la consulta SQL nunca lo usaria como filtro. |
| **Impacto** | Busqueda de productos por color imposible. Si el usuario pregunta "polo azul", la BD retorna todos los polos sin filtrar por color. |
| **Prioridad** | ALTA |
| **Soluciones** | 1. Leer `color` del plan del Planner. 2. Pasarlo a `db.buscar_producto(color=color)`. 3. La BD ya soporta el filtro (lineas 182-184 de `database.py`). |

### PROBLEMA 3: El Responder no recibe el precio en el JSON

| Campo | Valor |
|---|---|
| **Archivo** | `src/responder.py` |
| **Funcion** | `generate_response_with_history()` (lineas 182-192) |
| **Causa** | El JSON que se construye para enviar al Responder incluye `encontrado`, `cantidad_disponible`, `variantes_disponibles` pero NO incluye `precio`. La regla 11 del prompt dice "menciona el precio si esta disponible en el JSON" pero el precio nunca se envia en el JSON. |
| **Impacto** | Cuando el usuario pregunta "cuanto cuesta?", el Responder no tiene el precio en el JSON y puede alucinarlo o decir "no tengo el precio". |
| **Prioridad** | ALTA |
| **Soluciones** | 1. Agregar `"precio": resultado_inventario.get("precio")` al `input_data` del Responder. 2. El pipeline ya tiene el precio en `inventario.get("_precio")` pero no lo pasa al Responder. 3. Actualizar el prompt del Responder para mencionar el campo `precio` del JSON. |

### PROBLEMA 4: El historial se actualiza DESPUES de la consulta al Responder

| Campo | Valor |
|---|---|
| **Archivo** | `src/pipeline.py` |
| **Funcion** | `procesar_mensaje()` (lineas 274-280 vs 320) |
| **Causa** | El Responder recibe `self._historial_chat` en la linea 279, pero el historial se actualiza al final en la linea 320. Esto significa que el Responder no ve el mensaje ACTUAL del cliente en el historial — solo ve los mensajes previos. El mensaje actual va como `user_message` por separado, lo cual es correcto, pero el Responder no ve su propia respuesta anterior en el historial cuando genera la nueva respuesta. |
| **Impacto** | El Responder no tiene contexto de lo que el mismo respondio en el turno inmediatamente anterior, lo que puede causar respuestas repetitivas o inconsistentes. |
| **Prioridad** | MEDIA |
| **Soluciones** | 1. El orden actual (Planner -> BD -> Responder -> actualizar historial) es arquitectonicamente correcto. El problema es que el Responder recibe el historial SIN el turno actual. Considerar pasar el historial + el mensaje actual como un solo bloque. 2. Alternativa: actualizar el historial ANTES de llamar al Responder, incluyendo el mensaje del cliente, para que el Responder vea el contexto completo. |

### PROBLEMA 5: `_ultima_busqueda` se limpia cuando no se encuentra un producto

| Campo | Valor |
|---|---|
| **Archivo** | `src/pipeline.py` |
| **Funcion** | `procesar_mensaje()` (linea 262) |
| **Causa** | `self._ultima_busqueda = None` cuando `encontrado=False`. Si el usuario pregunta "y en talla 40?" y la talla 40 no existe en la BD, la memoria se borra. Si luego pregunta "y la 42?", el fallback ya no tiene memoria. |
| **Impacto** | Perdida de contexto despues de una consulta fallida. El fallback de emergencia deja de funcionar. |
| **Prioridad** | MEDIA |
| **Soluciones** | 1. NO limpiar `_ultima_busqueda` cuando el producto no se encuentra. Mantener la ultima busqueda exitosa. 2. Solo limpiar cuando el usuario cambie explicitamente de producto. |

### PROBLEMA 6: El fallback de emergencia no reconsulta la BD

| Campo | Valor |
|---|---|
| **Archivo** | `src/pipeline.py` |
| **Funcion** | `_fallback_seguimiento()` (lineas 84-140) |
| **Causa** | El fallback usa `self._ultima_busqueda` (memoria estatica) en vez de volver a consultar la BD con los nuevos atributos. Si el usuario dice "y en talla 40?" y la memoria tiene talla 42, el fallback responde con los datos de la talla 42, no consulta la talla 40 en la BD. |
| **Impacto** | Respuestas incorrectas cuando el usuario cambia atributos en el seguimiento. El fallback dice "Tenemos 3 unidades de Nike zapatillas talla 42" cuando el usuario pregunto por la talla 40. |
| **Prioridad** | ALTA |
| **Soluciones** | 1. El fallback deberia construir un plan con los atributos heredados + los nuevos, y llamar a `consultar_stock(plan)` para reconsultar la BD. 2. Solo usar la memoria estatica si la BD no encuentra nada. |

### PROBLEMA 7: `database.buscar_producto()` suma stock de todas las variantes

| Campo | Valor |
|---|---|
| **Archivo** | `src/database.py` |
| **Funcion** | `buscar_producto()` (linea 197) |
| **Causa** | `total_stock = sum(r["stock"] for r in exactos)` — suma el stock de TODAS las filas que coinciden con los filtros, no solo la especifica. Si el usuario pregunta por "zapatillas Nike talla 42" y hay 2 filas que coinciden (talla 40 con stock 5 y talla 42 con stock 3), el total_stock sera 8, no 3. Esto ocurre porque el `LIKE` en la consulta SQL puede coincidir con multiples filas. |
| **Impacto** | Cantidad incorrecta reportada al usuario. El usuario pregunta por talla 42 y se le dice "tenemos 8 unidades" cuando en realidad son 3 de la talla 42. |
| **Prioridad** | ALTA |
| **Soluciones** | 1. Si hay filtros de talla+marca+color, retornar solo el stock de la fila exacta, no la suma. 2. Si no hay filtros especificos, la suma es correcta (stock total del producto). 3. Distinguir entre "stock exacto" y "stock total" en el resultado. |

### PROBLEMA 8: `_format_variantes()` oculta variantes agotadas

| Campo | Valor |
|---|---|
| **Archivo** | `src/database.py` |
| **Funcion** | `_format_variantes()` (lineas 316-342) |
| **Causa** | Solo muestra variantes con `stock > 0` (linea 332). Si el usuario pregunta "que tallas tienen?", las tallas agotadas no aparecen. |
| **Impacto** | Informacion incompleta sobre variantes. El usuario no sabe que existe una talla que esta agotada. |
| **Prioridad** | BAJA |
| **Soluciones** | 1. Mostrar todas las variantes pero marcar las agotadas como "agotada". 2. O mantener el comportamiento actual (solo mostrar disponibles) si es decision de negocio. |

### PROBLEMA 9: El Planner mezcla extraccion de entidades con generacion de lenguaje

| Campo | Valor |
|---|---|
| **Archivo** | `src/planner.py` |
| **Funcion** | `PlannerOutput` (lineas 56-83) |
| **Causa** | El campo `mensaje_aclaracion` es texto generado por el LLM (generacion de lenguaje), mientras que los demas campos son extraccion de entidades. Esto mezcla dos tareas cognitivas distintas en un solo LLM call, lo que puede causar que el modelo confunda instrucciones. |
| **Impacto** | Cuando el Planner debe pedir aclaracion, a veces genera texto adicional en lugar de JSON puro, o el texto de aclaracion es generico. |
| **Prioridad** | MEDIA |
| **Soluciones** | 1. Separar en dos calls: el primer call extrae entidades (accion, producto, marca, talla, color), y si `accion=pedir_aclaracion`, un segundo call genera el mensaje de aclaracion. 2. Alternativa: mantener un solo call pero hacer el campo `mensaje_aclaracion` mas explicito en el prompt. |

### PROBLEMA 10: El prompt del Planner no tiene ejemplos de "que tallas tienen?"

| Campo | Valor |
|---|---|
| **Archivo** | `prompts/planner_prompt.txt` |
| **Funcion** | Seccion "Ejemplos de SEGUIMIENTO" (lineas 26-47) |
| **Causa** | Los ejemplos de seguimiento cubren "y en talla 40?", "cuantas unidades", "cuanto cuesta", "y de otro color", pero NO cubren "que tallas tienen?" o "solo negro?" — preguntas que piden listar atributos disponibles. |
| **Impacto** | El Planner puede clasificar estas preguntas como `no_relacionado` porque no calzan los patrones de los ejemplos. |
| **Prioridad** | MEDIA |
| **Soluciones** | 1. Agregar ejemplos few-shot: "que tallas tienen?" -> consultar_stock con talla=null. 2. Agregar "solo negro?" -> consultar_stock con color="negro". 3. Agregar "de que colores?" -> consultar_stock con color=null. |

### PROBLEMA 11: El Responder recibe `producto_buscado` con orden invertido

| Campo | Valor |
|---|---|
| **Archivo** | `src/pipeline.py` |
| **Funcion** | `procesar_mensaje()` (lineas 266-268) |
| **Causa** | `producto_buscado = f"{plan['marca']} {producto_buscado}"` — si el plan tiene marca="Nike" y producto="zapatillas", el Responder recibe "Nike zapatillas" en vez de "zapatillas Nike". El orden marca+producto es antinatural en espanol. |
| **Impacto** | Respuestas con orden de palabras incorrecto ("Nike zapatillas" en vez de "zapatillas Nike"). |
| **Prioridad** | BAJA |
| **Soluciones** | 1. Cambiar a `f"{producto_buscado} {plan['marca']}"` para que sea "zapatillas Nike". 2. O mejor: pasar producto y marca como campos separados al Responder. |

---

## Hoja de Ruta Priorizada

| # | Problema | Prioridad | Archivos a modificar |
|---|---|---|---|
| 1 | Schema sin campo `color` | ALTA | `src/planner.py`, `prompts/planner_prompt.txt` |
| 2 | `inventario.py` ignora color | ALTA | `src/inventario.py` |
| 3 | Responder no recibe precio | ALTA | `src/responder.py`, `src/pipeline.py`, `prompts/responder_prompt.txt` |
| 4 | Fallback no reconsulta BD | ALTA | `src/pipeline.py` |
| 5 | BD suma stock de variantes | ALTA | `src/database.py` |
| 6 | `_ultima_busqueda` se limpia | MEDIA | `src/pipeline.py` |
| 7 | Historial se actualiza tarde | MEDIA | `src/pipeline.py` |
| 8 | Planner mezcla tareas | MEDIA | `src/planner.py` (futuro) |
| 9 | Prompt sin ejemplos de atributos | MEDIA | `prompts/planner_prompt.txt` |
| 10 | Variantes agotadas ocultas | BAJA | `src/database.py` |
| 11 | Orden invertido producto+marca | BAJA | `src/pipeline.py` |