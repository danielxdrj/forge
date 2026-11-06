import pytest

from forge_core.app import main, start
from forge_core.errors import AutomationDisabledError, ConfigError


def test_start_refuses_when_automation_disabled():
    with pytest.raises(AutomationDisabledError):
        start({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "false"})


def test_start_runs_when_variable_absent():
    assert start({"FORGE_CONFIG_DIR": "x"}).automation_enabled is True


def test_start_invalid_value_is_config_error():
    with pytest.raises(ConfigError):
        start({"FORGE_CONFIG_DIR": "x", "FORGE_AUTOMATION_ENABLED": "talvez"})


def test_main_exits_nonzero_when_disabled(monkeypatch, capsys):
    monkeypatch.setenv("FORGE_CONFIG_DIR", "x")
    monkeypatch.setenv("FORGE_AUTOMATION_ENABLED", "false")
    assert main() != 0
    assert "FORGE_AUTOMATION_ENABLED" in capsys.readouterr().err
