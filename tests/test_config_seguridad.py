"""
Tests de configuracion segura por entorno (C2 / C3).
Verifican que FLASK_HOST y FLASK_DEBUG no caen a valores inseguros
por defecto, y que respetan configuracion explicita del entorno.
No requieren Ollama ni servidor Flask corriendo.
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload_config(monkeypatch, env: dict):
    """Recarga src.config con variables de entorno controladas."""
    for key in ("FLASK_HOST", "FLASK_DEBUG"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    if "src.config" in sys.modules:
        del sys.modules["src.config"]
    return importlib.import_module("src.config")


class TestFlaskHostSeguro:
    """Pruebas para C3: FLASK_HOST no debe exponerse por defecto."""

    def test_sin_flask_host_no_usa_0000(self, monkeypatch):
        """Sin FLASK_HOST en el entorno, NO debe caer a 0.0.0.0."""
        config = _reload_config(monkeypatch, {})
        assert config.FLASK_HOST != "0.0.0.0"
        assert config.FLASK_HOST == "127.0.0.1"

    def test_flask_host_explicito_127(self, monkeypatch):
        """FLASK_HOST=127.0.0.1 debe respetarse."""
        config = _reload_config(monkeypatch, {"FLASK_HOST": "127.0.0.1"})
        assert config.FLASK_HOST == "127.0.0.1"

    def test_flask_host_explicito_0000_se_respeta(self, monkeypatch):
        """Si se declara explicitamente 0.0.0.0, debe respetarse (decision consciente)."""
        config = _reload_config(monkeypatch, {"FLASK_HOST": "0.0.0.0"})
        assert config.FLASK_HOST == "0.0.0.0"

    def test_flask_host_explicito_ip_lan(self, monkeypatch):
        """Un host especifico (ej. IP de LAN) debe respetarse tal cual."""
        config = _reload_config(monkeypatch, {"FLASK_HOST": "192.168.1.47"})
        assert config.FLASK_HOST == "192.168.1.47"


class TestFlaskDebugSeguro:
    """Pruebas de regresion para C2 (mismo mecanismo reutilizado en C3)."""

    def test_sin_flask_debug_queda_desactivado(self, monkeypatch):
        config = _reload_config(monkeypatch, {})
        assert config.FLASK_DEBUG is False

    def test_flask_debug_true_se_activa(self, monkeypatch):
        config = _reload_config(monkeypatch, {"FLASK_DEBUG": "true"})
        assert config.FLASK_DEBUG is True