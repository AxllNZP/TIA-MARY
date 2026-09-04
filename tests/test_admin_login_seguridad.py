"""
Tests de seguridad para /admin/login y /admin/logout.
Cubre: CSRF (synchronizer token), limite de intentos por IP, y logout
protegido (POST + CSRF), implementados en la ronda de hardening.
"""

import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from werkzeug.security import generate_password_hash

PASSWORD_VALIDA = "clave_de_prueba_123"


def _cargar_app(monkeypatch):
    """
    Recarga src.config y src.api con ADMIN_PASSWORD_HASH y FLASK_SECRET_KEY
    controlados, ya que api.py los lee al momento de importarse.
    """
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", generate_password_hash(PASSWORD_VALIDA))
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave_de_sesion_para_tests")

    for mod in ("src.config", "src.api"):
        if mod in sys.modules:
            del sys.modules[mod]

    return importlib.import_module("src.api")


def _extraer_csrf_token(html: bytes) -> str:
    """Extrae el valor del input hidden csrf_token de una respuesta HTML."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html.decode("utf-8"))
    assert match, "No se encontro csrf_token en el HTML de la respuesta"
    return match.group(1)


class TestLoginCSRF:
    """Pruebas del token CSRF (synchronizer token pattern) en /admin/login."""

    def test_post_sin_csrf_token_rechaza(self, monkeypatch):
        """POST sin csrf_token debe rechazar sin evaluar la contraseña."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp = client.post("/admin/login", data={"password": PASSWORD_VALIDA})
        assert resp.status_code == 200
        assert b"Tu sesion de login expiro" in resp.data

    def test_post_con_csrf_token_invalido_rechaza(self, monkeypatch):
        """Token CSRF que no coincide con el de la sesion debe rechazar."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        client.get("/admin/login")  # crea la sesion con su propio csrf_token
        resp = client.post(
            "/admin/login",
            data={"password": PASSWORD_VALIDA, "csrf_token": "token_inventado"},
        )
        assert resp.status_code == 200
        assert b"Tu sesion de login expiro" in resp.data

    def test_post_con_csrf_token_valido_y_password_correcta_autentica(self, monkeypatch):
        """Token CSRF valido + password correcta debe autenticar y redirigir."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp_get = client.get("/admin/login")
        token = _extraer_csrf_token(resp_get.data)

        resp_post = client.post(
            "/admin/login",
            data={"password": PASSWORD_VALIDA, "csrf_token": token},
        )
        assert resp_post.status_code == 302
        assert resp_post.headers["Location"] == "/admin"

        # Confirmar que la sesion realmente quedo autenticada
        resp_admin = client.get("/admin")
        assert resp_admin.status_code == 200

    def test_csrf_invalido_no_cuenta_como_intento_fallido(self, monkeypatch):
        """
        Repetir POSTs con CSRF invalido no debe agotar el limite de intentos:
        un login legitimo posterior debe seguir funcionando sin bloqueo.
        """
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp_get = client.get("/admin/login")
        token = _extraer_csrf_token(resp_get.data)

        # Mas intentos que LOGIN_MAX_INTENTOS, todos con CSRF invalido
        for _ in range(api_module.LOGIN_MAX_INTENTOS + 2):
            resp = client.post(
                "/admin/login",
                data={"password": PASSWORD_VALIDA, "csrf_token": "token_invalido"},
            )
            assert b"Cuenta bloqueada" not in resp.data

        # El login legitimo, con el token correcto, debe seguir funcionando
        resp_final = client.post(
            "/admin/login",
            data={"password": PASSWORD_VALIDA, "csrf_token": token},
        )
        assert resp_final.status_code == 302
        assert resp_final.headers["Location"] == "/admin"


class TestLoginRateLimitPorIP:
    """Pruebas del limite de intentos fallidos particionado por IP."""

    def test_bloquea_tras_max_intentos_con_password_incorrecta(self, monkeypatch):
        """Tras LOGIN_MAX_INTENTOS fallos, la siguiente peticion debe bloquear."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp_get = client.get("/admin/login")
        token = _extraer_csrf_token(resp_get.data)

        for _ in range(api_module.LOGIN_MAX_INTENTOS):
            resp = client.post(
                "/admin/login",
                data={"password": "password_incorrecta", "csrf_token": token},
            )
        assert b"Cuenta bloqueada temporalmente" in resp.data

        # Un intento adicional, incluso con la password correcta, debe rechazar
        resp_bloqueado = client.post(
            "/admin/login",
            data={"password": PASSWORD_VALIDA, "csrf_token": token},
        )
        assert b"Demasiados intentos fallidos" in resp_bloqueado.data

    def test_ips_distintas_tienen_contadores_independientes(self, monkeypatch):
        """Agotar el limite desde una IP no debe afectar el contador de otra IP."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp_get = client.get("/admin/login")
        token = _extraer_csrf_token(resp_get.data)

        for _ in range(api_module.LOGIN_MAX_INTENTOS):
            client.post(
                "/admin/login",
                data={"password": "password_incorrecta", "csrf_token": token},
                environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
            )

        # Misma app, IP distinta: no deberia estar bloqueada
        resp_get_otra_ip = client.get(
            "/admin/login", environ_overrides={"REMOTE_ADDR": "10.0.0.2"}
        )
        token_otra_ip = _extraer_csrf_token(resp_get_otra_ip.data)
        resp = client.post(
            "/admin/login",
            data={"password": PASSWORD_VALIDA, "csrf_token": token_otra_ip},
            environ_overrides={"REMOTE_ADDR": "10.0.0.2"},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/admin"


class TestLogout:
    """Pruebas del endpoint /admin/logout (POST + CSRF + login requerido)."""

    def _login(self, api_module, client):
        resp_get = client.get("/admin/login")
        token = _extraer_csrf_token(resp_get.data)
        client.post("/admin/login", data={"password": PASSWORD_VALIDA, "csrf_token": token})

    def test_logout_por_get_rechaza(self, monkeypatch):
        """GET /admin/logout ya no debe ser un metodo permitido."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()
        self._login(api_module, client)

        resp = client.get("/admin/logout")
        assert resp.status_code == 405

    def test_logout_sin_sesion_redirige_a_login(self, monkeypatch):
        """POST /admin/logout sin sesion activa debe redirigir a login, no fallar."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()

        resp = client.post("/admin/logout", data={"csrf_token": "cualquiera"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/admin/login"

    def test_logout_con_csrf_valido_cierra_sesion(self, monkeypatch):
        """Logout con token CSRF valido debe cerrar la sesion realmente."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()
        self._login(api_module, client)

        resp_admin = client.get("/admin")
        token = _extraer_csrf_token(resp_admin.data)

        resp_logout = client.post("/admin/logout", data={"csrf_token": token})
        assert resp_logout.status_code == 302
        assert resp_logout.headers["Location"] == "/admin/login"

        # La sesion ya no debe dar acceso al panel
        resp_admin_despues = client.get("/admin")
        assert resp_admin_despues.status_code == 302
        assert resp_admin_despues.headers["Location"] == "/admin/login"

    def test_logout_con_csrf_invalido_no_cierra_sesion(self, monkeypatch):
        """Logout con token CSRF invalido no debe cerrar la sesion."""
        api_module = _cargar_app(monkeypatch)
        client = api_module.app.test_client()
        self._login(api_module, client)

        resp_logout = client.post("/admin/logout", data={"csrf_token": "token_invalido"})
        assert resp_logout.status_code == 302
        assert resp_logout.headers["Location"] == "/admin"

        # La sesion debe seguir activa
        resp_admin = client.get("/admin")
        assert resp_admin.status_code == 200