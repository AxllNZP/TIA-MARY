"""
Orquestador del pipeline completo:
Planner -> Inventario -> Responder -> Registro.
Integra el motor de aprendizaje para inyectar pautas en los prompts.
Pasa historial de conversacion real al Planner y al Responder.
Mantiene memoria conversacional por sesion que conserva el contexto
y actualiza unicamente los atributos que cambian, sin perder los anteriores.
"""

from typing import Optional

from . import database as db
from .config import NOMBRE_TIENDA
from .inventario import consultar_stock, consultar_catalogo
from .learning import engine as learning_engine
from .ollama_client import OllamaClient
from .planner import Planner
from .responder import Responder
from .session_store import session_store


# Productos que la tienda NO vende (para respuestas rapidas sin LLM)
PRODUCTOS_FUERA_CONTEXTO = [
    "laptop", "laptops", "computadora", "pc", "tablet", "celular", "telefono",
    "iphone", "samsung", "playstation", "ps5", "ps4", "xbox", "nintendo",
    "televisor", "tv", "smart tv", "refrigerador", "lavadora", "microondas",
    "moto", "carro", "bicicleta", "comida", "pollo", "hamburguesa", "pizza",
    "perfume", "maquillaje", "juguete", "libro", "mueble", "silla", "mesa",
    "herramienta", "medicina", "alimento",
]

# Palabras clave para detectar preguntas de seguimiento (fallback de emergencia)
PALABRAS_SEGUIMIENTO = [
    "cuantas", "cuantos", "cuanto", "cuanta",
    "unidades", "cantidad", "disponibles",
    "precio", "cuesta", "vale", "cuanto esta",
    "talla", "tallas", "otra talla", "otro color",
    "y de", "y el", "y la", "otra", "otro",
    "tambien", "ademas", "solo", "blanco", "negro", "rojo", "azul",
]

# Palabras clave para detectar consultas de catalogo (sin LLM, 100% confiable)
PALABRAS_CATALOGO = [
    "que venden", "que productos", "catalogo", "catalogo completo",
    "muestrame lo que", "que tienen", "que hay", "lista de productos",
    "que ofrecen", "que clases de", "que tipo de productos",
    "que ropa tienen", "que calzado tienen", "que accesorios tienen",
]


class Pipeline:
    """
    Orquesta el flujo completo de procesamiento de un mensaje de WhatsApp.
    Pasa historial de conversacion real al Planner y al Responder.
    Mantiene memoria conversacional por sesion (atributos heredados).
    """

    def __init__(self, client: Optional[OllamaClient] = None):
        self.client = client or OllamaClient()
        self.planner = Planner(client=self.client)
        self.responder = Responder(client=self.client)
        # Contexto e historial ya NO son estado de instancia: se leen/escriben
        # por session_id via session_store, aislados entre usuarios.
        # Historial de chat: ultimos 10 mensajes (5 turnos cliente+asistente)

    def _refresh_pautas(self):
        """Refresca las pautas desde la BD (se llama antes de cada consulta)."""
        self._pautas_planner_cache = learning_engine.get_pautas_planner()
        self._pautas_responder_cache = learning_engine.get_pautas_responder()

    def _es_producto_fuera_contexto(self, mensaje: str) -> Optional[str]:
        """Detecta si el mensaje pregunta por un producto que la tienda no vende."""
        msg = mensaje.lower()
        for p in PRODUCTOS_FUERA_CONTEXTO:
            if p in msg:
                return p
        return None

    def _es_consulta_catalogo(self, mensaje: str) -> bool:
        """
        Detecta si el mensaje es una consulta de catalogo general
        ("que venden?", "muestrame el catalogo", etc.).
        Se hace sin LLM para 100% de confiabilidad y cero latencia.
        """
        msg = mensaje.lower().strip()
        return any(p in msg for p in PALABRAS_CATALOGO)

    def _parece_seguimiento(self, mensaje: str, contexto: dict) -> bool:
        """
        Detecta si el mensaje parece una pregunta de seguimiento.
        Se usa como fallback de emergencia cuando el Planner devuelve no_relacionado
        pero hay contexto previo en la sesion.
        """
        if not contexto.get("producto"):
            return False
        msg = mensaje.lower().strip()
        return len(msg.split()) <= 6 and any(p in msg for p in PALABRAS_SEGUIMIENTO)

    def _merge_atributos(self, plan: dict, contexto: dict) -> dict:
        """
        Fusiona los atributos del plan del Planner con el contexto de sesion.
        Solo actualiza los atributos que el Planner extrajo (no None).
        Los atributos None se heredan del contexto anterior.
        """
        merged = dict(contexto)  # Copiar contexto actual

        # Actualizar solo los atributos que el Planner extrajo
        for key in ["producto", "marca", "talla", "color", "modelo", "material", "genero"]:
            value = plan.get(key)
            if value is not None:
                merged[key] = value

        # Si el producto cambio, resetear atributos especificos
        if plan.get("producto") and plan.get("producto") != contexto.get("producto"):
            # El usuario cambio de producto: resetear atributos no mencionados
            for key in ["marca", "talla", "color", "modelo", "material", "genero"]:
                if plan.get(key) is None:
                    merged[key] = None

        return merged

    def _fallback_seguimiento(self, mensaje: str, contexto: dict) -> dict:
        """
        Fallback de emergencia: genera una respuesta directa usando el contexto
        de sesion. Se activa solo cuando el Planner con historial devuelve
        no_relacionado pero el mensaje parece de seguimiento.
        """
        b = contexto
        msg = mensaje.lower().strip()

        if any(p in msg for p in ["cuantas", "cuantos", "unidades", "cantidad", "disponibles"]):
            if b.get("cantidad_disponible") and b["cantidad_disponible"] > 0:
                respuesta = (
                    f"Tenemos {b['cantidad_disponible']} unidad(es) de {b.get('marca') or ''} {b.get('producto')}"
                    f"{' talla ' + b['talla'] if b.get('talla') else ''}"
                    f"{' color ' + b['color'] if b.get('color') else ''} disponibles en {NOMBRE_TIENDA}."
                )
            else:
                respuesta = (
                    f"Por el momento no tenemos stock de {b.get('marca') or ''} {b.get('producto')}"
                    f"{' talla ' + b['talla'] if b.get('talla') else ''} en {NOMBRE_TIENDA}."
                )
        elif any(p in msg for p in ["precio", "cuesta", "vale", "cuanto esta"]):
            if b.get("precio"):
                respuesta = (
                    f"El precio de {b.get('marca') or ''} {b.get('producto')}"
                    f"{' talla ' + b['talla'] if b.get('talla') else ''} "
                    f"es de S/ {b['precio']:.2f} en {NOMBRE_TIENDA}."
                )
            else:
                respuesta = f"No tengo el precio exacto en este momento en {NOMBRE_TIENDA}."
        elif any(p in msg for p in ["talla", "tallas", "otra talla", "otro color", "color", "colores"]):
            if b.get("variantes"):
                variantes_str = ", ".join(b["variantes"][:6])
                respuesta = f"Tenemos disponibles estas variantes de {b.get('producto')}: {variantes_str}."
            else:
                respuesta = f"De {b.get('producto')} solo tenemos la talla {b.get('talla', 'unica')}."
        else:
            respuesta = (
                f"De {b.get('marca') or ''} {b.get('producto')}"
                f"{' talla ' + b['talla'] if b.get('talla') else ''} "
                f"tenemos {b.get('cantidad_disponible') or 0} unidades en {NOMBRE_TIENDA}."
            )

        return {
            "mensaje_cliente": mensaje,
            "respuesta": respuesta,
            "planificacion": {
                "accion": "consultar_stock_seguimiento",
                "producto": b.get("producto"),
                "marca": b.get("marca"),
            },
            "inventario": {
                "encontrado": True,
                "cantidad_disponible": b.get("cantidad_disponible"),
            },
            "consulta_id": None,
            "error": None,
        }

    def procesar_mensaje(self, mensaje: str, session_id: str = "default") -> dict:
        """
        Procesa un mensaje completo a traves del pipeline.
        Pasa el historial de conversacion real al Planner y al Responder.
        Mantiene memoria conversacional por sesion, aislada via session_id.
        """
        resultado = {
            "mensaje_cliente": mensaje,
            "respuesta": None,
            "planificacion": None,
            "inventario": None,
            "consulta_id": None,
            "error": None,
        }
        mensaje_lower = mensaje.lower().strip()
        contexto = session_store.get_contexto(session_id)
        historial = session_store.get_historial(session_id)
        
        try:
            self._refresh_pautas()

            # === 0. DETECTAR CONSULTA DE CATALOGO (sin LLM, 100% confiable) ===
            # Si el cliente pregunta "que venden?" o "muestrame el catalogo",
            # responder directamente con datos de la BD sin pasar por el LLM.
            # Esto evita latencia y garantiza que la respuesta tenga datos reales.
            if self._es_consulta_catalogo(mensaje):
                catalogo = consultar_catalogo()
                respuesta = (
                    f"Hola! En {NOMBRE_TIENDA} manejamos:"
                    f"{catalogo['catalogo_texto']}"
                    f"\n\nTe interesa algo en particular?"
                )
                resultado["respuesta"] = respuesta
                resultado["planificacion"] = {"accion": "consultar_catalogo", "producto": None}
                resultado["consulta_id"] = db.registrar_consulta(
                    mensaje_cliente=mensaje,
                    accion="consultar_catalogo",
                    encontrado=True,
                    respuesta_enviada=respuesta,
                )
                self._actualizar_historial(session_id, mensaje, respuesta)
                return resultado

            # === 1. FILTRO RAPIDO: Producto fuera de contexto (sin LLM) ===
            fuera_contexto = self._es_producto_fuera_contexto(mensaje)
            if fuera_contexto:
                respuesta = (
                    f"Hola! En {NOMBRE_TIENDA} nos especializamos en ropa, calzado y accesorios. "
                    f"No manejamos {fuera_contexto}. "
                    f"Puedo ayudarte con zapatillas, polos, jeans, medias, gorras o casacas. "
                    f"Que estas buscando?"
                )
                resultado["respuesta"] = respuesta
                resultado["planificacion"] = {"accion": "fuera_contexto", "producto": fuera_contexto}
                resultado["consulta_id"] = db.registrar_consulta(
                    mensaje_cliente=mensaje,
                    accion="fuera_contexto",
                    producto_buscado=fuera_contexto,
                    encontrado=False,
                    respuesta_enviada=respuesta,
                )
                self._actualizar_historial(session_id, mensaje, respuesta)
                return resultado

            # === 2. PLANNER con historial real + salida estructurada ===
            prompt_con_pautas = self.planner.system_prompt
            if self._pautas_planner_cache:
                prompt_con_pautas += "\n" + self._pautas_planner_cache

            plan = self.planner.classify_with_history(
                mensaje=mensaje,
                history=historial,
                system_prompt=prompt_con_pautas,
            )
            resultado["planificacion"] = plan

            # === 3. Si no es consultar_stock ===
            if plan["accion"] != "consultar_stock":
                # FALLBACK DE EMERGENCIA: si el Planner dice no_relacionado pero
                # el mensaje parece de seguimiento y hay contexto, usar fallback
                if plan["accion"] == "no_relacionado" and self._parece_seguimiento(mensaje, contexto):
                    resultado = self._fallback_seguimiento(mensaje, contexto)
                    resultado["consulta_id"] = db.registrar_consulta(
                        mensaje_cliente=mensaje,
                        accion="consultar_stock",
                        producto_buscado=contexto.get("producto"),
                        marca_buscada=contexto.get("marca"),
                        encontrado=True,
                        respuesta_enviada=resultado["respuesta"],
                    )
                    self._actualizar_historial(session_id, mensaje, resultado["respuesta"])
                    return resultado

                # Respuestas para pedir_aclaracion y no_relacionado
                if plan["accion"] == "pedir_aclaracion":
                    # Usar atributo_faltante si esta disponible, sino mensaje_aclaracion
                    atributo = plan.get("atributo_faltante")
                    if atributo:
                        respuesta = f"Para ayudarte mejor, podrias indicarme el {atributo} del producto que buscas?"
                    elif plan.get("mensaje_aclaracion"):
                        respuesta = plan["mensaje_aclaracion"]
                    else:
                        respuesta = "Para ayudarte, podrias darme mas detalles del producto que buscas?"
                elif plan["accion"] == "no_relacionado":
                    if plan.get("producto"):
                        respuesta = (
                            f"Hola! En {NOMBRE_TIENDA} nos especializamos en ropa, calzado y accesorios. "
                            f"No manejamos {plan['producto']}. "
                            f"Puedo ayudarte con zapatillas, polos, jeans, medias, gorras o casacas. "
                            f"Que estas buscando?"
                        )
                    else:
                        respuesta = (
                            f"Hola! Bienvenido a {NOMBRE_TIENDA}. "
                            f"Soy tu asistente virtual y estoy aqui para ayudarte a consultar "
                            f"disponibilidad y precios de nuestros productos. "
                            f"Que estas buscando hoy?"
                        )
                else:
                    respuesta = (
                        f"Hola! Bienvenido a {NOMBRE_TIENDA}. "
                        f"Estoy aqui para ayudarte a consultar la disponibilidad de nuestros productos. "
                        f"Que estas buscando?"
                    )
                resultado["respuesta"] = respuesta
                resultado["consulta_id"] = db.registrar_consulta(
                    mensaje_cliente=mensaje,
                    accion=plan["accion"],
                    producto_buscado=plan.get("producto"),
                    marca_buscada=plan.get("marca"),
                    talla_buscada=plan.get("talla_o_variante"),
                    encontrado=False,
                    respuesta_enviada=respuesta,
                )
                self._actualizar_historial(session_id, mensaje, respuesta)
                return resultado

            # === 4. Merge de atributos con contexto de sesion ===
            merged_plan = self._merge_atributos(plan, contexto)

            # === 5. Consultar inventario real (SQLite) con atributos merged ===
            inventario = consultar_stock(merged_plan)
            resultado["inventario"] = inventario

            # === 6. Actualizar contexto de sesion (Problema 5: NO limpiar si no se encuentra) ===
            if inventario.get("encontrado"):
                contexto = {
                    "producto": merged_plan.get("producto"),
                    "marca": merged_plan.get("marca"),
                    "talla": merged_plan.get("talla"),
                    "color": merged_plan.get("color"),
                    "modelo": merged_plan.get("modelo"),
                    "material": merged_plan.get("material"),
                    "genero": merged_plan.get("genero"),
                    "cantidad_disponible": inventario.get("cantidad_disponible"),
                    "variantes": inventario.get("variantes_disponibles"),
                    "precio": inventario.get("precio") or inventario.get("_precio"),
                }
                session_store.set_contexto(session_id, contexto)
            # NO limpiar contexto si no se encuentra — mantener el anterior (Problema 5)

            # === 7. Generar respuesta con historial ===
            if inventario.get("encontrado"):
                # Problema 11: orden correcto producto+marca (no marca+producto)
                producto_buscado = merged_plan.get("producto") or "producto"
                if merged_plan.get("marca"):
                    producto_buscado = f"{producto_buscado} {merged_plan['marca']}"
                if merged_plan.get("talla"):
                    producto_buscado = f"{producto_buscado} talla {merged_plan['talla']}"
                if merged_plan.get("color"):
                    producto_buscado = f"{producto_buscado} color {merged_plan['color']}"

                prompt_responder_con_pautas = self.responder.system_prompt
                if self._pautas_responder_cache:
                    prompt_responder_con_pautas += "\n" + self._pautas_responder_cache

                respuesta = self.responder.generate_response_with_history(
                    system_prompt=prompt_responder_con_pautas,
                    mensaje_cliente=mensaje,
                    producto_buscado=producto_buscado,
                    resultado_inventario=inventario,
                    history=historial,
                )
            else:
                # Producto no encontrado — ofrecer variantes si hay
                if contexto.get("variantes"):
                    variantes_str = ", ".join(contexto["variantes"][:5])
                    respuesta = (
                        f"No encontre {merged_plan.get('producto') or 'ese producto'}"
                        f"{' de la marca ' + merged_plan['marca'] if merged_plan.get('marca') else ''}"
                        f"{' talla ' + merged_plan['talla'] if merged_plan.get('talla') else ''}"
                        f"{' color ' + merged_plan['color'] if merged_plan.get('color') else ''} "
                        f"en {NOMBRE_TIENDA}. "
                        f"Tenemos disponibles: {variantes_str}."
                    )
                else:
                    respuesta = (
                        f"Lo siento, no encontre {merged_plan.get('producto') or 'ese producto'}"
                        f"{' de la marca ' + merged_plan.get('marca') if merged_plan.get('marca') else ''} "
                        f"en {NOMBRE_TIENDA}. "
                        f"Puedo ayudarte a buscar algo similar si me dices que tipo de producto te interesa."
                    )

            resultado["respuesta"] = respuesta

            # === 8. Registrar consulta ===
            resultado["consulta_id"] = db.registrar_consulta(
                mensaje_cliente=mensaje,
                accion=plan["accion"],
                producto_buscado=merged_plan.get("producto"),
                marca_buscada=merged_plan.get("marca"),
                talla_buscada=merged_plan.get("talla"),
                producto_id=inventario.get("_producto_id"),
                encontrado=inventario.get("encontrado", False),
                respuesta_enviada=respuesta,
            )

        except Exception as e:
            resultado["error"] = str(e)
            resultado["respuesta"] = (
                f"Hola! En {NOMBRE_TIENDA} estamos listos para atenderte. "
                "Por el momento tuve un problemita para revisar el inventario, "
                "pero dime que buscas y te ayudo en un momento."
            )
            try:
                resultado["consulta_id"] = db.registrar_consulta(
                    mensaje_cliente=mensaje,
                    accion="error",
                    encontrado=False,
                    respuesta_enviada=resultado["respuesta"],
                )
            except Exception:
                pass

        self._actualizar_historial(session_id, mensaje, resultado.get("respuesta"))
        return resultado

    def _actualizar_historial(self, session_id: str, mensaje_cliente: str, respuesta: str | None):
        """Actualiza el historial de chat de la sesion con el mensaje del cliente y la respuesta."""
        session_store.append_historial(session_id, mensaje_cliente, respuesta)


# Instancia global para la API
pipeline = Pipeline()