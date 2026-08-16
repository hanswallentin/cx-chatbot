import os
from functools import lru_cache

import yaml


@lru_cache
def load_config() -> dict:
    config_path = os.environ.get("CONFIG_PATH", "/config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def llm_api_key() -> str | None:
    config = load_config()
    return os.environ.get(config["llm"]["api_key_env"])


def llm_settings() -> dict:
    return load_config()["llm"]


def mcp_server_url() -> str:
    config = load_config()
    mcp_cfg = config["services"]["mcp_server"]
    base = os.environ.get("MCP_SERVER_URL") or mcp_cfg["internal_url"]
    return base.rstrip("/") + mcp_cfg["mcp_path"]


def guardrails_settings() -> dict:
    return load_config()["guardrails"]


def policy_text() -> dict:
    return load_config()["policy"]


def feature_flags() -> dict:
    return load_config()["feature_flags"]


def log_level() -> str:
    config = load_config()
    env_name = config["logging"]["level_env"]
    return os.environ.get(env_name) or config["logging"]["default_level"]
