"""
Modulo de inventario: capa de negocio entre el Planner y la base de datos.
Traduce el resultado del Planner en una consulta SQL y retorna el formato
que espera el Responder.
"""

from typing import Optional

from . import database as db


def _limpiar_nombre_producto(nombre: str | None, marca: str | None) -> tuple[str | None, str | None]:
    """
    Limpia el nombre del producto cuando el Planner junta producto+marca.
    
    Ejemplo: si nombre="zapatillas Nike" y marca="Nike",
    devuelve nombre="zapatillas", marca="Nike".
    
    Tambien normaliza tallas embebidas en el nombre.
    """
    if not nombre:
        return nombre, marca
    
    nombre_limpio = nombre.strip().lower()
    
    # Si la marca esta duplicada en el nombre, quitarla
    if marca:
        marca_lower = marca.strip().lower()
        # Quitar la marca del nombre si aparece
        palabras = nombre_limpio.split()
        palabras_filtradas = [p for p in palabras if p != marca_lower]
        if palabras_filtradas:
            nombre_limpio = " ".join(palabras_filtradas)
    
    # Si el "producto" es en realidad una marca conocida (ej: "lacoste"),
    # inferir el tipo de producto desde la base de datos
    marcas_conocidas = ["nike", "adidas", "lacoste", "levi's", "levis", "puma",
                        "new era", "newera", "tommy hilfiger", "tommy", "north face",
                        "northface"]
    if nombre_limpio in marcas_conocidas or nombre_limpio.replace("'", "") in marcas_conocidas:
        # El "producto" es una marca, debemos inferir el tipo de producto
        # Buscar en la BD que productos tiene esa marca
        productos_de_marca = db._get_productos_por_marca(nombre_limpio)
        if productos_de_marca:
            # Usar el primer tipo de producto encontrado
            nombre_limpio = productos_de_marca[0]
        # La marca ya esta en el campo marca (o la inferimos)
        if not marca:
            marca = nombre_limpio

    # Normalizar nombres comunes con variaciones
    sinonimos = {
        "zapatilla": "zapatillas",
        "zapato": "zapatillas",
        "tenis": "zapatillas",
        "zapatos": "zapatillas",
        "zapatill": "zapatillas",
        "polo": "polo",
        "polos": "polo",
        "camisa": "polo",
        "jean": "jean",
        "jeans": "jean",
        "pantalon": "jean",
        "pantalones": "jean",
        "medias": "medias",
        "media": "medias",
        "calcetin": "medias",
        "calcetines": "medias",
        "gorra": "gorra",
        "gorras": "gorra",
        "casaca": "casaca",
        "casacas": "casaca",
        "chaqueta": "casaca",
        "chompa": "casaca",
        "chompas": "casaca",
        "abrigo": "casaca",
    }
    
    # Intentar mapear el nombre a un sinonimo conocido (solo palabras completas)
    palabras = nombre_limpio.split()
    for i, palabra in enumerate(palabras):
        # Buscar coincidencia exacta de palabra en sinonimos
        if palabra in sinonimos:
            palabras[i] = sinonimos[palabra]
        else:
            # Buscar si alguna clave de sinonimo coincide como palabra completa
            for clave, valor in sinonimos.items():
                if palabra == clave:
                    palabras[i] = valor
                    break
    nombre_limpio = " ".join(palabras)
    
    return nombre_limpio, marca


def consultar_stock(plan: dict) -> dict:
    """
    Consulta el inventario real (SQLite) basado en la clasificacion del Planner.

    Args:
        plan: Resultado del Planner con producto, marca, talla, color, etc.

    Returns:
        Diccionario con la estructura esperada por el Responder:
        {
            "encontrado": bool,
            "cantidad_disponible": int | None,
            "variantes_disponibles": list[str] | None,
            "precio": float | None,
        }
    """
    nombre = plan.get("producto")
    marca = plan.get("marca")
    talla = plan.get("talla") or plan.get("talla_o_variante")  # Retrocompatibilidad
    color = plan.get("color")  # NUEVO: leer color del plan
    
    # Limpiar nombre y marca (evitar duplicados)
    nombre, marca = _limpiar_nombre_producto(nombre, marca)
    
    # Limpiar talla: quitar prefijos como "talla " o "t."
    if talla:
        talla = talla.strip().lower()
        talla = talla.replace("talla ", "").replace("t. ", "").replace("t ", "").strip()

    # Limpiar color
    if color:
        color = color.strip().lower()

    resultado = db.buscar_producto(
        nombre=nombre,
        marca=marca,
        talla=talla,
        color=color,  # NUEVO: pasar el color a la BD
    )

    return {
        "encontrado": resultado.get("encontrado", False),
        "cantidad_disponible": resultado.get("cantidad_disponible"),
        "variantes_disponibles": resultado.get("variantes_disponibles"),
        "precio": resultado.get("precio"),  # Renombrado de _precio a precio
        "_precio": resultado.get("precio"),  # Retrocompatibilidad
        "_producto_id": resultado.get("producto_id"),
    }


def consultar_catalogo() -> dict:
    """
    Consulta el catalogo completo de productos y lo formatea como texto
    legible para mostrar al cliente. Agrupa por categoria y marca, indicando
    stock disponible o agotado.

    Returns:
        Diccionario con la estructura:
        {
            "catalogo_texto": str,  # Texto formateado listo para mostrar
            "total_categorias": int,
            "total_productos": int,
        }
    """
    catalogo = db.get_catalogo()

    lineas = []
    for cat in catalogo:
        categoria = cat["categoria"]
        lineas.append(f"\n{categoria.capitalize()}:")

        # Agrupar por nombre+marca para no repetir variantes
        productos_vistos = set()
        for p in cat["productos"]:
            key = f"{p['nombre']} - {p['marca']}"
            if key not in productos_vistos:
                productos_vistos.add(key)
                # Verificar si hay stock en alguna variante de este producto+marca
                stock_total = sum(
                    vp["stock"]
                    for vp in cat["productos"]
                    if vp["nombre"] == p["nombre"] and vp["marca"] == p["marca"]
                )
                if stock_total > 0:
                    lineas.append(f"  - {p['nombre']} {p['marca']} ({stock_total} unidades)")
                else:
                    lineas.append(f"  - {p['nombre']} {p['marca']} (agotado)")

    return {
        "catalogo_texto": "\n".join(lineas),
        "total_categorias": len(catalogo),
        "total_productos": sum(len(c["productos"]) for c in catalogo),
    }
