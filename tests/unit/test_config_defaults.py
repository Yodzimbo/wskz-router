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
