import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

REPO_ROOT = Path(__file__).parents[2]
API_BASE = "http://testserver"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(REPO_ROOT / "config.yaml"))
    monkeypatch.setenv("API_BASE_URL", API_BASE)
    import config

    config.load_config.cache_clear()
    yield
    config.load_config.cache_clear()


@pytest.fixture
def api_base() -> str:
    return API_BASE
