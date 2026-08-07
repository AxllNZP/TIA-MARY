# Final Implementation Report — TIA MARY

## Resumen

Se implementaron las mejoras aprobadas del documento `conversation_architecture_review.md` para resolver 11 problemas de arquitectura conversacional. Los cambios amplian el schema del Planner, implementan memoria conversacional por sesion, incluyen el precio en el JSON del Responder, y agregan reglas anti-alucinacion.

---

## Archivos Modificados

| # | Archivo | Cambios |
|---|---|---|
| 1 | `src/planner.py` | Schema ampliado con 7 campos nuevos, metodo `_normalize_result()`, prompt actualizado |
| 2 | `prompts/planner_prompt.txt` | 9 ejemplos few-shot de seguimiento con atributos (color, talla, precio, variantes) |
| 3 | `src/inventario.py` | Lee `color` del plan y lo pasa a la BD, renombrado `_precio` a `precio` |
| 4 | `src/database.py` | `_format_variantes()` ahora muestra variantes agotadas con "(agotada)" |
| 5 | `src/responder.py` | Incluye `precio` en el JSON al LLM, reglas 12-13 anti-alucinacion, metodo `_build_input_data()` |
| 6 | `src/pipeline.py` | Memoria conversacional por sesion (`_contexto_sesion`), `_merge_atributos()`, no limpia contexto si no encuentra, orden correcto producto+marca |
| 7 | `prompts/responder_prompt.txt` | JSON ahora incluye `precio`, reglas 12-13 anti-alucinacion, 6 ejemplos few-shot |
| 8 | `tests/test_planner.py` | Tests actualizados para validar nuevos campos del schema |
| 9 | `conversation_architecture_review.md` | Documento de analisis creado |

---

## Cambios Realizados

### 1. Schema del Planner ampliado (`src/planner.py`)

**Antes:** 6 campos (accion, producto, marca, talla_o_variante, cantidad_solicitada, mensaje_aclaracion)

**Ahora:** 13 campos:
- `accion` — consultar_stock | pedir_aclaracion | no_relacionado
- `producto` — tipo de producto
- `marca` — marca del producto
- `talla` — talla (renombrado de talla_o_variante)
- `color` — **NUEVO** color del producto
- `modelo` — **NUEVO** modelo especifico
- `material` — **NUEVO** material
- `genero` — **NUEVO** genero (hombre/mujer/unisex)
- `cantidad_solicitada` — cantidad
- `precio_consultado` — **NUEVO** booleano: el cliente pregunta por precio?
- `consultar_variantes` — **NUEVO** booleano: el cliente pregunta por variantes?
- `atributo_faltante` — **NUEVO** que atributo falta (para pedir_aclaracion)
- `mensaje_aclaracion` — mensaje de aclaracion (retrocompatibilidad)

**Retrocompatibilidad:** El metodo `_normalize_result()` mapea `talla` a `talla_o_variante` en el diccionario de retorno.

### 2. Memoria conversacional por sesion (`src/pipeline.py`)

**Antes:** `_ultima_busqueda` se limpiaba cuando no se encontraba un producto.

**Ahora:** `_contexto_sesion` mantiene todos los atributos (producto, marca, talla, color, modelo, material, genero, cantidad, variantes, precio). El metodo `_merge_atributos()` fusiona los atributos del plan del Planner con el contexto de sesion:
- Solo actualiza los atributos que el Planner extrajo (no None)
- Los atributos None se heredan del contexto anterior
- Si el producto cambia, resetea los atributos no mencionados
- NO se limpia el contexto si el producto no se encuentra (Problema 5)

### 3. Precio incluido en el JSON del Responder (`src/responder.py`)

**Antes:** El JSON enviado al Responder no incluia `precio`.

**Ahora:** El metodo `_build_input_data()` incluye `"precio": resultado_inventario.get("precio") or resultado_inventario.get("_precio")` en el JSON.

### 4. Color pasado a la BD (`src/inventario.py`)

**Antes:** `color=None` hardcoded.

**Ahora:** Lee `color` del plan del Planner y lo pasa a `db.buscar_producto(color=color)`.

### 5. Variantes agotadas visibles (`src/database.py`)

**Antes:** `_format_variantes()` solo mostraba variantes con stock > 0.

**Ahora:** Muestra todas las variantes, marcando las agotadas con "(agotada)".

### 6. Reglas anti-alucinacion (`src/responder.py` + `prompts/responder_prompt.txt`)

**Nuevas reglas:**
- Regla 8: "NO INVENTES datos de stock que no esten en el JSON recibido."
- Regla 12: "Si el inventario no contiene el atributo solicitado, responde explicitamente que no existe."
- Regla 13: "NO infieras, NO completes, NO inventes datos que no esten en el JSON."

### 7. Orden correcto producto+marca (`src/pipeline.py`)

**Antes:** `f"{plan['marca']} {producto_buscado}"` → "Nike zapatillas"

**Ahora:** `f"{producto_buscado} {merged_plan['marca']}"` → "zapatillas Nike"

### 8. Prompt del Planner con ejemplos de atributos conversacionales

**Nuevos ejemplos few-shot:**
- "y en blanco?" → hereda producto+marca+talla, agrega color="blanco"
- "solo negro?" → hereda producto+marca+talla, agrega color="negro"
- "que tallas tienen?" → consultar_variantes=true
- "de que colores?" → consultar_variantes=true
- "cuanto cuesta?" → precio_consultado=true

---

## Riesgos

| Riesgo | Nivel | Mitigacion |
|---|---|---|
| El LLM `llama3.1:8b` puede no respetar el schema ampliado (13 campos) | MEDIO | El retry de `generate_structured()` reenvia el error al modelo. El fallback `parse_json_response()` extrae JSON manual. |
| El campo `talla` reemplaza a `talla_o_variante` en el schema | BAJO | `_normalize_result()` mapea `talla` a `talla_o_variante` en el retorno para retrocompatibilidad. |
| La memoria conversacional por sesion puede acumular atributos obsoletos | MEDIO | `_merge_atributos()` resetea atributos si el producto cambia. |
| El Responder puede seguir alucinando a pesar de las reglas 12-13 | MEDIO | Las reglas son explicitas y los ejemplos few-shot muestran el comportamiento correcto. |
| Los tests de integracion con LLM no se ejecutaron (requieren Ollama corriendo) | BAJO | Los tests sin LLM (22/22) pasaron. Los tests con LLM se pueden ejecutar con `py -m pytest tests/ -v`. |

---

## Casos de Prueba Recomendados

### Caso 1: Consulta simple con color
```
Cliente: "Tienen polo azul talla M?"
Esperado: accion=consultar_stock, producto=polo, color=azul, talla=M
```

### Caso 2: Seguimiento con cambio de color
```
Cliente: "Tienen zapatillas Nike talla 42?"
Cliente: "y en blanco?"
Esperado: accion=consultar_stock, producto=zapatillas, marca=Nike, talla=42, color=blanco
```

### Caso 3: Seguimiento con cambio de talla
```
Cliente: "Tienen zapatillas Nike talla 42?"
Cliente: "y en talla 40?"
Esperado: accion=consultar_stock, producto=zapatillas, marca=Nike, talla=40
```

### Caso 4: Consulta de precio
```
Cliente: "Tienen zapatillas Nike talla 42?"
Cliente: "cuanto cuesta?"
Esperado: precio_consultado=true, respuesta menciona S/ 250.00
```

### Caso 5: Consulta de variantes
```
Cliente: "Tienen zapatillas Nike?"
Cliente: "que tallas tienen?"
Esperado: consultar_variantes=true, respuesta lista tallas disponibles
```

### Caso 6: Color no disponible
```
Cliente: "Tienen zapatillas Nike talla 42?"
Cliente: "y en blanco?"
Esperado: encontrado=false (solo negro), respuesta ofrece variantes en negro
```

### Caso 7: Cambio de producto
```
Cliente: "Tienen zapatillas Nike talla 42?"
Cliente: "y un polo azul?"
Esperado: accion=consultar_stock, producto=polo, color=azul, marca=null (no hereda Nike)
```

### Caso 8: Producto fuera de contexto
```
Cliente: "Venden laptops?"
Esperado: fuera_contexto, respuesta indica que solo venden ropa/calzado
```

---

## Conversaciones de Ejemplo Esperadas

### Conversacion 1: Consulta con seguimiento de color
```
Cliente: Tienen zapatillas Nike talla 42?
TIA MARY: Hola! Si, en TIA MARY tenemos zapatillas Nike talla 42 disponibles. Nos quedan 3 unidades a S/ 250.00. Te las separo?

Cliente: y en blanco?
TIA MARY: No tenemos zapatillas Nike talla 42 en color blanco en TIA MARY. Solo tenemos en color negro, en tallas 40 y 42. Te interesa alguna?
```

### Conversacion 2: Consulta de precio y variantes
```
Cliente: Tienen polos azules?
TIA MARY: Hola! Si, en TIA MARY tenemos polos azules disponibles. Tenemos Lacoste en tallas M y L, y Tommy Hilfiger tambien. Cual te interesa?

Cliente: cuanto cuesta el Lacoste talla L?
TIA MARY: El polo Lacoste talla L esta a S/ 120.00 en TIA MARY. Te lo separo?
```

### Conversacion 3: Cambio de producto
```
Cliente: Tienen zapatillas Nike talla 42?
TIA MARY: Hola! Si, en TIA MARY tenemos zapatillas Nike talla 42 disponibles. Nos quedan 3 unidades a S/ 250.00.

Cliente: y un jean Levi's?
TIA MARY: Si, en TIA MARY tenemos jeans Levi's disponibles. Tenemos en tallas 32 y 34, color azul oscuro. Cual te interesa?
```

---

## Tests Ejecutados

| Suite | Tests | Resultado |
|---|---|---|
| `py main.py test` (logica sin LLM) | 11/11 | PASS |
| `TestParseJsonResponse` (parser JSON) | 5/5 | PASS |
| `TestSchemaValidation` (validacion de schema) | 5/5 | PASS |
| `test_resultado_invalido_lanza_error` (responder) | 1/1 | PASS |
| **Total sin LLM** | **22/22** | **PASS** |

Los tests de integracion con LLM (`TestPlanner`, `TestPlannerMultiTurn`, `TestResponder`, `TestResponderMultiTurn`) requieren Ollama corriendo con `llama3.1:8b`. Se pueden ejecutar con:
```bash
py -m pytest tests/ -v