import re
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_default_model_is_consistent() -> None:
    # The model name lives in four literals; a mismatch breaks ollama-init or /health.
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    compose_defaults = re.findall(r"OLLAMA_MODEL:-([^}]+)\}", compose)
    env_defaults = re.findall(r"^OLLAMA_MODEL=(\S+)$", env_example, flags=re.MULTILINE)
    settings_default = Settings.model_fields["ollama_model"].default

    assert len(compose_defaults) == 2  # ollama-init pulls it, api checks it in /health
    assert len(env_defaults) == 1
    assert {*compose_defaults, *env_defaults} == {settings_default}


def test_api_env_defaults_match_settings() -> None:
    # `${VAR:-x}` in the api service must equal the Settings default, so running the app
    # outside compose (tests, uvicorn on the host) behaves like the container.
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", 1)[1].split("\nvolumes:", 1)[0]
    defaults = re.findall(r"\$\{([A-Z_]+):-([^}]*)\}", api_service)

    assert {name for name, _ in defaults} >= {"OLLAMA_MODEL", "AGENT_TIMEOUT_S", "AGENT_RETRIES"}
    for name, raw in defaults:
        field = name.lower()
        assert field in Settings.model_fields, name
        assert getattr(Settings(**{field: raw}), field) == Settings.model_fields[field].default, (
            name
        )
