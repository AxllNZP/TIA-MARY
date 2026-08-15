"""
Módulo de base de datos SQLite para TÍA MARY.
Gestiona el inventario, historial de consultas y feedback de aprendizaje.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DATABASE_PATH, SEED_DATA_PATH


def _get_data_dir() -> Path:
    """Asegura que el directorio data existe."""
    data_dir = Path(DATABASE_PATH).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _get_connection() -> sqlite3.Connection:
    """Obtiene una conexión a la base de datos."""
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Inicializa la base de datos: crea tablas si no existen."""
    _get_data_dir()
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                marca TEXT DEFAULT NULL,
                talla TEXT DEFAULT NULL,
                color TEXT DEFAULT NULL,
                precio REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0,
                categoria TEXT DEFAULT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mensaje_cliente TEXT NOT NULL,
                accion TEXT NOT NULL,
                producto_buscado TEXT DEFAULT NULL,
                marca_buscada TEXT DEFAULT NULL,
                talla_buscada TEXT DEFAULT NULL,
                producto_id INTEGER DEFAULT NULL,
                encontrado INTEGER NOT NULL DEFAULT 0,
                respuesta_enviada TEXT DEFAULT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                consulta_id INTEGER NOT NULL,
                calificacion TEXT NOT NULL DEFAULT 'neutral',
                comentario TEXT DEFAULT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (consulta_id) REFERENCES consultas(id)
            );

            CREATE TABLE IF NOT EXISTS pautas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL DEFAULT 'general',
                contenido TEXT NOT NULL,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos(nombre);
            CREATE INDEX IF NOT EXISTS idx_productos_marca ON productos(marca);
            CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria);
            CREATE INDEX IF NOT EXISTS idx_consultas_timestamp ON consultas(timestamp);
            CREATE INDEX IF NOT EXISTS idx_feedback_consulta ON feedback(consulta_id);
        """)
        conn.commit()
    finally:
        conn.close()


def seed_from_json() -> int:
    """
    Carga productos desde el archivo JSON semilla.
    Solo inserta si la tabla está vacía.

    Returns:
        Número de productos insertados.
    """
    seed_path = Path(SEED_DATA_PATH)
    if not seed_path.exists():
        return 0

    conn = _get_connection()
    try:
        # Verificar si ya hay datos
        count = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        if count > 0:
            return 0

        data = json.loads(seed_path.read_text(encoding="utf-8"))
        productos = data.get("productos", [])

        insertados = 0
        for p in productos:
            conn.execute(
                """
                INSERT INTO productos (nombre, marca, talla, color, precio, stock, categoria)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["nombre"],
                    p.get("marca"),
                    p.get("talla"),
                    p.get("color"),
                    p.get("precio", 0),
                    p.get("stock", 0),
                    p.get("categoria"),
                ),
            )
            insertados += 1

        conn.commit()
        return insertados
    finally:
        conn.close()


def buscar_producto(
    nombre: Optional[str] = None,
    marca: Optional[str] = None,
    talla: Optional[str] = None,
    color: Optional[str] = None,
) -> dict:
    """
    Busca productos en el inventario.

    Args:
        nombre: Nombre del producto (zapatillas, polo, jean...)
        marca: Marca del producto (Nike, Adidas...)
        talla: Talla o variante (40, M, única...)
        color: Color del producto

    Returns:
        Diccionario con la estructura:
        {
            "encontrado": bool,
            "producto_id": int | None,
            "cantidad_disponible": int | None,
            "precio": float | None,
            "variantes_disponibles": list[str] | None,
        }
    """
    conn = _get_connection()
    try:
        # Construir query base
        conditions = ["activo = 1"]
        params = []

        if nombre:
            conditions.append("LOWER(nombre) LIKE ?")
            params.append(f"%{nombre.lower()}%")

        if marca:
            conditions.append("LOWER(marca) = ?")
            params.append(marca.lower())

        if talla:
            conditions.append("LOWER(talla) = ?")
            params.append(talla.lower())

        if color:
            conditions.append("LOWER(color) = ?")
            params.append(color.lower())

        where_clause = " AND ".join(conditions)

        # Buscar coincidencia exacta (todos los filtros)
        cursor = conn.execute(
            f"SELECT * FROM productos WHERE {where_clause}",
            params,
        )
        exactos = cursor.fetchall()

        if exactos:
            # Producto encontrado con todos los filtros
            total_stock = sum(r["stock"] for r in exactos)
            primer_producto = exactos[0]

            # Recolectar variantes (tallas/colores del mismo producto+marca)
            variantes = _get_variantes(conn, nombre, marca)
            variantes_str = _format_variantes(variantes, exactos)

            return {
                "encontrado": True,
                "producto_id": primer_producto["id"],
                "cantidad_disponible": total_stock,
                "precio": primer_producto["precio"],
                "variantes_disponibles": variantes_str,
                "producto_exacto": dict(primer_producto),
            }

        # Fallback 1: Busqueda parcial por nombre, manteniendo los demas
        # filtros ya especificados (marca, talla, color) como exactos.
        if nombre:
            fallback_conditions = ["activo = 1", "LOWER(nombre) LIKE ?"]
            fallback_params = [f"%{nombre.lower()}%"]

            if marca:
                fallback_conditions.append("LOWER(marca) = ?")
                fallback_params.append(marca.lower())
            if talla:
                fallback_conditions.append("LOWER(talla) = ?")
                fallback_params.append(talla.lower())
            if color:
                fallback_conditions.append("LOWER(color) = ?")
                fallback_params.append(color.lower())

            cursor = conn.execute(
                f"SELECT * FROM productos WHERE {' AND '.join(fallback_conditions)}",
                fallback_params,
            )
            parciales = cursor.fetchall()

            if parciales:
                total_stock = sum(r["stock"] for r in parciales)
                primer_producto = parciales[0]
                variantes = _get_variantes(conn, nombre, marca)
                variantes_str = _format_variantes(variantes, parciales)

                return {
                    "encontrado": True,
                    "producto_id": primer_producto["id"],
                    "cantidad_disponible": total_stock,
                    "precio": primer_producto["precio"],
                    "variantes_disponibles": variantes_str,
                }

            # Fallback 2: Si el nombre es compuesto (ej: "zapatillas nike"),
            # intentar con cada palabra individual, manteniendo marca/talla/color
            # ya especificados como filtros exactos.
            palabras = nombre.lower().split()
            if len(palabras) > 1:
                for palabra in palabras:
                    if len(palabra) < 3:
                        continue  # ignorar palabras muy cortas

                    palabra_conditions = ["activo = 1", "LOWER(nombre) LIKE ?"]
                    palabra_params = [f"%{palabra}%"]

                    if marca:
                        palabra_conditions.append("LOWER(marca) = ?")
                        palabra_params.append(marca.lower())
                    if talla:
                        palabra_conditions.append("LOWER(talla) = ?")
                        palabra_params.append(talla.lower())
                    if color:
                        palabra_conditions.append("LOWER(color) = ?")
                        palabra_params.append(color.lower())

                    cursor = conn.execute(
                        f"SELECT * FROM productos WHERE {' AND '.join(palabra_conditions)}",
                        palabra_params,
                    )
                    parciales = cursor.fetchall()
                    if parciales:
                        total_stock = sum(r["stock"] for r in parciales)
                        primer_producto = parciales[0]
                        variantes = _get_variantes(conn, palabra, marca)
                        variantes_str = _format_variantes(variantes, parciales)

                        return {
                            "encontrado": True,
                            "producto_id": primer_producto["id"],
                            "cantidad_disponible": total_stock,
                            "precio": primer_producto["precio"],
                            "variantes_disponibles": variantes_str,
                        }

        # No encontrado
        return {
            "encontrado": False,
            "producto_id": None,
            "cantidad_disponible": None,
            "precio": None,
            "variantes_disponibles": None,
        }
    finally:
        conn.close()


def _get_variantes(
    conn: sqlite3.Connection, nombre: Optional[str], marca: Optional[str]
) -> list[dict]:
    """Obtiene todas las variantes de un producto (tallas y colores)."""
    conditions = ["activo = 1"]
    params = []

    if nombre:
        conditions.append("LOWER(nombre) LIKE ?")
        params.append(f"%{nombre.lower()}%")
    if marca:
        conditions.append("LOWER(marca) LIKE ?")
        params.append(f"%{marca.lower()}%")

    where_clause = " AND ".join(conditions)
    cursor = conn.execute(
        f"SELECT DISTINCT talla, color, stock, marca, precio FROM productos WHERE {where_clause} ORDER BY talla",
        params,
    )
    return [dict(row) for row in cursor.fetchall()]


def _get_productos_por_marca(marca: str) -> list[str]:
    """
    Retorna los tipos de producto (nombres unicos) asociados a una marca.

    Args:
        marca: Nombre de la marca (ej: "lacoste", "nike").

    Returns:
        Lista de nombres de producto (ej: ["polo"] para Lacoste).
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT DISTINCT nombre FROM productos WHERE activo = 1 AND LOWER(marca) LIKE ?",
            [f"%{marca.lower()}%"],
        )
        return [row["nombre"] for row in cursor.fetchall()]
    finally:
        conn.close()


def _format_variantes(
    variantes: list[dict], exactos: list[dict]
) -> Optional[list[str]]:
    """Formatea las variantes como strings legibles, incluyendo agotadas."""
    result = []

    # Primero añadir los exactos que coinciden con los filtros
    exactos_ids = {r["id"] for r in exactos} if exactos and "id" in exactos[0].keys() else set()

    for v in variantes:
        talla = v.get("talla", "")
        color = v.get("color", "")
        stock = v.get("stock", 0)
        marca = v.get("marca", "")
        precio = v.get("precio", 0)

        parts = []
        if marca:
            parts.append(marca)
        if talla:
            parts.append(f"talla {talla}")
        if color:
            parts.append(f"color {color}")
        if stock == 0:
            parts.append("(agotada)")
        result.append(" - ".join(parts))

    return result if result else None


def registrar_consulta(
    mensaje_cliente: str,
    accion: str,
    producto_buscado: Optional[str] = None,
    marca_buscada: Optional[str] = None,
    talla_buscada: Optional[str] = None,
    producto_id: Optional[int] = None,
    encontrado: bool = False,
    respuesta_enviada: Optional[str] = None,
) -> int:
    """
    Registra una consulta en el historial.

    Returns:
        ID de la consulta registrada.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO consultas (mensaje_cliente, accion, producto_buscado,
                marca_buscada, talla_buscada, producto_id, encontrado, respuesta_enviada)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mensaje_cliente,
                accion,
                producto_buscado,
                marca_buscada,
                talla_buscada,
                producto_id,
                1 if encontrado else 0,
                respuesta_enviada,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def guardar_feedback(
    consulta_id: int,
    calificacion: str,
    comentario: Optional[str] = None,
) -> None:
    """
    Guarda feedback sobre una respuesta.

    Args:
        consulta_id: ID de la consulta.
        calificacion: 'positiva', 'negativa', o 'neutral'.
        comentario: Comentario opcional con la corrección sugerida.
    """
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO feedback (consulta_id, calificacion, comentario)
            VALUES (?, ?, ?)
            """,
            (consulta_id, calificacion, comentario),
        )
        conn.commit()
    finally:
        conn.close()


def guardar_pauta(tipo: str, contenido: str) -> int:
    """
    Guarda una pauta de mejora en el sistema.

    Args:
        tipo: 'planner', 'responder', o 'general'.
        contenido: Texto de la pauta.

    Returns:
        ID de la pauta creada.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO pautas (tipo, contenido) VALUES (?, ?)",
            (tipo, contenido),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_pautas_activas(tipo: Optional[str] = None) -> list[dict]:
    """
    Obtiene las pautas activas, opcionalmente filtradas por tipo.
    Ordena por creado_en DESC, con id DESC como desempate: creado_en tiene
    resolucion de 1 segundo (datetime('now') de SQLite), por lo que varias
    pautas creadas en el mismo segundo necesitan id (autoincremental) para
    determinar cual es realmente mas reciente.
    """
    conn = _get_connection()
    try:
        if tipo:
            cursor = conn.execute(
                "SELECT * FROM pautas WHERE activo = 1 AND tipo = ? ORDER BY creado_en DESC, id DESC",
                (tipo,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM pautas WHERE activo = 1 ORDER BY creado_en DESC, id DESC"
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_ultimas_consultas(limit: int = 20) -> list[dict]:
    """Obtiene las últimas consultas con su feedback."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT c.*, f.calificacion as feedback_calificacion, f.comentario as feedback_comentario
            FROM consultas c
            LEFT JOIN feedback f ON f.consulta_id = c.id
            ORDER BY c.timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_estadisticas() -> dict:
    """Obtiene estadísticas básicas del sistema."""
    conn = _get_connection()
    try:
        total_consultas = conn.execute("SELECT COUNT(*) FROM consultas").fetchone()[0]
        total_productos = conn.execute(
            "SELECT COUNT(*) FROM productos WHERE activo = 1"
        ).fetchone()[0]
        total_con_stock = conn.execute(
            "SELECT COUNT(*) FROM productos WHERE activo = 1 AND stock > 0"
        ).fetchone()[0]

        positivas = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE calificacion = 'positiva'"
        ).fetchone()[0]
        negativas = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE calificacion = 'negativa'"
        ).fetchone()[0]

        return {
            "total_consultas": total_consultas,
            "total_productos": total_productos,
            "productos_con_stock": total_con_stock,
            "feedback_positivo": positivas,
            "feedback_negativo": negativas,
            "pautas_activas": conn.execute(
                "SELECT COUNT(*) FROM pautas WHERE activo = 1"
            ).fetchone()[0],
        }
    finally:
        conn.close()


def get_catalogo() -> list[dict]:
    """
    Retorna un resumen del catalogo agrupado por categoria.
    Cada categoria contiene sus productos con marca, talla, color, stock y precio.
    Solo incluye productos activos.

    Returns:
        Lista de diccionarios con la estructura:
        [
            {
                "categoria": "calzado",
                "productos": [
                    {"nombre": "zapatillas", "marca": "Nike", "talla": "42", "color": "negro", "stock": 3, "precio": 250.0},
                    ...
                ]
            },
            ...
        ]
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT categoria, nombre, marca, talla, color, stock, precio
            FROM productos
            WHERE activo = 1
            ORDER BY categoria, nombre, marca, talla
            """
        )
        filas = [dict(row) for row in cursor.fetchall()]

        # Agrupar por categoria
        catalogo = {}
        for f in filas:
            cat = f["categoria"] or "otros"
            if cat not in catalogo:
                catalogo[cat] = []
            catalogo[cat].append(f)

        return [
            {"categoria": k, "productos": v}
            for k, v in catalogo.items()
        ]
    finally:
        conn.close()
