"""Regression checks for the Settings configuration-style migration."""

import importlib
import os
from pathlib import Path
import subprocess
import sys


PROJECT_DIR = Path(__file__).resolve().parents[3]
SETTINGS_MODULE = "CLPainter.web.backend.app._config.settings"


def test_settings_cold_import_has_no_legacy_config_warning(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_DIR.parent)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    source = (
        "import warnings; "
        "from pydantic.warnings import PydanticDeprecatedSince20; "
        "warnings.simplefilter('error', PydanticDeprecatedSince20); "
        f"import {SETTINGS_MODULE}"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_settings_keeps_existing_config_options():
    settings_class = importlib.import_module(SETTINGS_MODULE).Settings
    assert settings_class.model_config["env_file"] == ".env"
    assert settings_class.model_config["case_sensitive"] is True
    assert settings_class.model_config["extra"] == "ignore"


def test_settings_preserves_dotenv_case_and_environment_precedence(tmp_path, monkeypatch):
    settings_class = importlib.import_module(SETTINGS_MODULE).Settings
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LOG_LEVEL=INFO\nlog_level=DEBUG\nUNKNOWN_CONFIG_OPTION=ignored\n", encoding="utf-8",
    )
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("log_level", raising=False)
    from_file = settings_class(_env_file=env_file)
    assert from_file.LOG_LEVEL == "INFO"
    assert "UNKNOWN_CONFIG_OPTION" not in from_file.model_dump()
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    assert settings_class(_env_file=env_file).LOG_LEVEL == "ERROR"
