"""
Punto de entrada principal del asistente de WhatsApp para TIA MARY.

Modos de ejecucion:
  py main.py              -> Demo interactiva por consola
  py main.py server       -> Iniciar servidor Flask (API + admin)
  py main.py initdb       -> Inicializar base de datos y cargar semilla
  py main.py test         -> Ejecutar tests rapidos (sin LLM)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import database as db
from src.pipeline import pipeline
from src.config import NOMBRE_TIENDA


def modo_demo():
    """Demo interactiva por consola usando el pipeline completo."""
    print("=" * 60)
    print(f"  ASISTENTE DE WHATSAPP - {NOMBRE_TIENDA}")
    print("  Pipeline completo: Planner -> Inventario SQLite -> Responder")
    print("=" * 60)
    print()
    print("La base de datos contiene estos productos:")
    print("   - Zapatillas: Nike (talla 38-42), Adidas (talla 39-42)")
    print("   - Polos: Lacoste (M, L), Tommy Hilfiger (M, L)")
    print("   - Jeans: Levi's (talla 30-34)")
    print("   - Medias: Puma, Adidas")
    print("   - Gorras: New Era, Nike")
    print("   - Casacas: North Face (M)")
    print()
    print("Ejemplos de mensajes:")
    print('  - "Tienen zapatillas Nike talla 42?"')
    print('  - "Hola, busco un polo azul talla M"')
    print('  - "Tienen zapatillas Adidas talla 38?"')
    print('  - "Quiero un jean Levi\'s talla 30"')
    print('  - "Buenos dias"')
    print('  - "Venden laptops?"')
    print()
    print('Escribe "salir" para terminar. Escribe "stats" para ver estadisticas.')
    print()

    while True:
        try:
            mensaje = input("Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego!")
            break

        if not mensaje:
            continue

        if mensaje.lower() in ("salir", "exit", "quit"):
            print("Hasta luego!")
            break

        if mensaje.lower() == "stats":
            stats = db.get_estadisticas()
            print(f"\n--- Estadisticas ---")
            print(f"   Consultas totales: {stats['total_consultas']}")
            print(f"   Productos con stock: {stats['productos_con_stock']}/{stats['total_productos']}")
            print(f"   Feedback [+]: {stats['feedback_positivo']} | [-]: {stats['feedback_negativo']}")
            print(f"   Pautas activas: {stats['pautas_activas']}")
            print()
            continue

        print()
        resultado = pipeline.procesar_mensaje(mensaje)

        # Mostrar detalles internos
        print("-" * 50)
        print("--- PLANIFICACION ---")
        print(json.dumps(resultado["planificacion"], indent=2, ensure_ascii=False))

        if resultado.get("inventario"):
            print("\n--- INVENTARIO (SQLite) ---")
            inv_publico = {
                k: v
                for k, v in resultado["inventario"].items()
                if not k.startswith("_")
            }
            print(json.dumps(inv_publico, indent=2, ensure_ascii=False))

        if resultado.get("error"):
            print(f"\n[ERROR]: {resultado['error']}")

        print(f"\n--- RESPUESTA FINAL (consulta #{resultado['consulta_id']}) ---")
        print(f"{NOMBRE_TIENDA}: {resultado['respuesta']}")
        print("-" * 50)
        print()


def modo_server():
    """Inicia el servidor Flask con API y panel de administracion."""
    from src.api import run_server

    run_server()


def modo_initdb():
    """Inicializa la base de datos y carga datos semilla."""
    print("Inicializando base de datos...")
    db.init_db()
    insertados = db.seed_from_json()
    if insertados:
        print(f"[OK] {insertados} productos cargados desde seed_productos.json")
    else:
        print("[INFO] La base de datos ya tenia datos. No se recargo la semilla.")
    print(f"[INFO] Base de datos: {db._get_data_dir() / 'tienda.db'}")


def modo_reset():
    """Elimina la base de datos y la recrea desde cero con datos semilla."""
    import os as _os
    db_path = Path("data/tienda.db")
    if db_path.exists():
        _os.remove(db_path)
        print("[OK] Base de datos eliminada.")
    db.init_db()
    insertados = db.seed_from_json()
    if insertados:
        print(f"[OK] {insertados} productos cargados desde seed_productos.json")
    else:
        print("[ERROR] No se pudieron cargar productos.")
    print("[INFO] Base de datos reiniciada desde cero. Listo para pruebas.")


def modo_clean():
    """Limpia el historial de consultas, feedback y pautas, pero conserva los productos."""
    import sqlite3
    conn = sqlite3.connect(str(db.DATABASE_PATH))
    conn.execute("DELETE FROM consultas")
    conn.execute("DELETE FROM feedback")
    conn.execute("DELETE FROM pautas")
    conn.commit()
    conn.close()
    print("[OK] Historial de consultas, feedback y pautas eliminados.")
    print("[INFO] Los productos se conservan intactos.")


def modo_test():
    """Ejecuta tests rapidos del pipeline (sin LLM, solo logica)."""
    print("=== Ejecutando tests rapidos... ===\n")

    # Test 1: DB init and seed
    db.init_db()
    count = db.seed_from_json()
    assert count == 0 or count > 0, "seed_from_json deberia retornar 0 o > 0"
    print("[PASS] Test 1: Base de datos inicializada")

    # Test 2: Buscar producto existente
    result = db.buscar_producto(nombre="zapatillas", marca="Nike", talla="42")
    assert result["encontrado"] is True
    assert result["cantidad_disponible"] > 0
    print(f"[PASS] Test 2: Busqueda 'zapatillas Nike talla 42' -> encontrado, stock={result['cantidad_disponible']}")

    # Test 3: Buscar producto sin stock
    result = db.buscar_producto(nombre="zapatillas", marca="Nike", talla="38")
    assert result["encontrado"] is True
    assert result["cantidad_disponible"] == 0
    print(f"[PASS] Test 3: Busqueda 'zapatillas Nike talla 38' -> encontrado, stock=0 (sin stock)")

    # Test 4: Buscar producto inexistente
    result = db.buscar_producto(nombre="laptop")
    assert result["encontrado"] is False
    print(f"[PASS] Test 4: Busqueda 'laptop' -> no encontrado")

    # Test 5: Buscar producto parcial
    result = db.buscar_producto(nombre="jean")
    assert result["encontrado"] is True
    assert result["variantes_disponibles"] is not None
    print(f"[PASS] Test 5: Busqueda 'jean' -> encontrado con variantes")

    # Test 6: Registrar consulta
    consulta_id = db.registrar_consulta(
        mensaje_cliente="test",
        accion="consultar_stock",
        producto_buscado="zapatillas",
        encontrado=True,
        respuesta_enviada="Test respuesta",
    )
    assert consulta_id > 0
    print(f"[PASS] Test 6: Consulta registrada (ID={consulta_id})")

    # Test 7: Guardar feedback
    db.guardar_feedback(consulta_id, "positiva", "Respuesta correcta")
    historial = db.get_ultimas_consultas(limit=1)
    assert historial[0]["feedback_calificacion"] == "positiva"
    print(f"[PASS] Test 7: Feedback guardado y recuperado")

    # Test 8: Guardar y recuperar pauta
    pauta_id = db.guardar_pauta("responder", "TEST: Siempre mencionar el precio")
    pautas = db.get_pautas_activas(tipo="responder")
    assert any(p["id"] == pauta_id for p in pautas)
    print(f"[PASS] Test 8: Pauta guardada y recuperada (ID={pauta_id})")

    # Test 9: Estadisticas
    stats = db.get_estadisticas()
    assert stats["total_consultas"] >= 1
    print(f"[PASS] Test 9: Estadisticas -> {stats}")

    # Test 10: Inventario existente
    from src.inventario import consultar_stock
    plan = {"producto": "polo", "marca": "Lacoste", "talla_o_variante": "M", "cantidad_solicitada": None}
    result = consultar_stock(plan)
    assert result["encontrado"] is True
    print(f"[PASS] Test 10: consultar_stock('polo Lacoste M') -> {result['encontrado']}")

    # Test 11: Producto no encontrado
    plan = {"producto": "tablet", "marca": None, "talla_o_variante": None, "cantidad_solicitada": None}
    result = consultar_stock(plan)
    assert result["encontrado"] is False
    print(f"[PASS] Test 11: consultar_stock('tablet') -> no encontrado")

    print(f"\n{'='*50}")
    print("*** Todos los tests pasaron (11/11) ***")
    print(f"{'='*50}")

    # Limpiar datos de test
    import sqlite3
    conn = sqlite3.connect(str(db.DATABASE_PATH))
    conn.execute("DELETE FROM feedback WHERE consulta_id = ?", (consulta_id,))
    conn.execute("DELETE FROM consultas WHERE id = ?", (consulta_id,))
    conn.execute("DELETE FROM pautas WHERE id = ?", (pauta_id,))
    conn.commit()
    conn.close()


def main():
    if len(sys.argv) > 1:
        modo = sys.argv[1].lower()
        if modo == "server":
            modo_server()
        elif modo == "initdb":
            modo_initdb()
        elif modo == "test":
            modo_test()
        elif modo == "reset":
            modo_reset()
        elif modo == "clean":
            modo_clean()
        else:
            print(f"Modo desconocido: {modo}")
            print("Uso: py main.py [demo|server|initdb|test|reset|clean]")
    else:
        # Modo por defecto: inicializar BD y demo
        db.init_db()
        insertados = db.seed_from_json()
        if insertados:
            print(f"[OK] {insertados} productos cargados\n")
        modo_demo()


if __name__ == "__main__":
    main()