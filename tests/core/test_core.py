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


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer xyz",
        "{'Authorization': 'Bearer xyz'}",
        "chamada falhou com Bearer xyz no cabecalho",
        "authorization=Basic xyz",
        "Authorization: token xyz",
    ],
)
def test_redact_authorization_value(text):
    from forge_core.logging import redact

    assert "xyz" not in redact(text)


def test_log_extra_authorization_dict_is_redacted():
    buf = io.StringIO()
    configure_logging("INFO", buf)
    logging.getLogger("forge_core.t").info("req", extra={"headers": {"Authorization": "Bearer xyz"}})
    assert "xyz" not in buf.getvalue()


def test_automation_flag_helpers():
    from forge_core.config import is_automation_enabled, require_automation_enabled
    from forge_core.errors import AutomationDisabledError

    on = load_settings({"FORGE_CONFIG_DIR": "x"})
    off = load_settings({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "false"})
    assert is_automation_enabled(on) and not is_automation_enabled(off)
    require_automation_enabled(on)
    with pytest.raises(AutomationDisabledError):
        require_automation_enabled(off)
