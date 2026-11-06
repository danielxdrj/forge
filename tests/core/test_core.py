import io
import json
import logging

import pytest

from forge_core.app import main, start
from forge_core.config import load_settings
from forge_core.errors import ConfigError
from forge_core.logging import configure_logging


def test_valid_config_starts():
    s = start({"FORGE_CONFIG_DIR": "/tmp/cfg.example.invalid"})
    assert s.log_level == "INFO" and s.automation_enabled


def test_missing_required_fails_clearly():
    with pytest.raises(ConfigError, match="FORGE_CONFIG_DIR"):
        load_settings({})


def test_reports_all_problems():
    with pytest.raises(ConfigError) as e:
        load_settings({"FORGE_LOG_LEVEL": "x", "FORGE_AUTOMATION_ENABLED": "talvez"})
    msg = str(e.value)
    assert "FORGE_CONFIG_DIR" in msg and "FORGE_LOG_LEVEL" in msg and "FORGE_AUTOMATION_ENABLED" in msg


def test_main_returns_1_without_config(monkeypatch, capsys):
    monkeypatch.delenv("FORGE_CONFIG_DIR", raising=False)
    assert main() == 1
    assert "FORGE_CONFIG_DIR" in capsys.readouterr().err


def test_log_is_json_and_redacts():
    buf = io.StringIO()
    configure_logging("INFO", buf)
    logging.getLogger("forge_core.t").info("login token=abc123", extra={"password": "p4ss"})
    data = json.loads(buf.getvalue())
    assert "abc123" not in buf.getvalue() and "p4ss" not in buf.getvalue()
    assert data["level"] == "INFO"
