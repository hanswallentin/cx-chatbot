import os
from functools import lru_cache

import yaml


@lru_cache
def load_config() -> dict:
    config_path = os.environ.get("CONFIG_PATH", "/config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def api_base_url() -> str:
    config = load_config()
    return os.environ.get("API_BASE_URL") or config["services"]["api"]["internal_url"]


def mcp_settings() -> dict:
    config = load_config()
    return config["services"]["mcp_server"]


def tool_descriptions() -> dict:
    config = load_config()
    return {t["name"]: t["description"].strip() for t in config["mcp"]["tools"]}
