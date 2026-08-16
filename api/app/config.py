"""Loads only the sections of config.yaml this service needs."""
import os
from functools import lru_cache

import yaml


@lru_cache
def load_config() -> dict:
    config_path = os.environ.get("CONFIG_PATH", "/config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def database_path() -> str:
    config = load_config()
    env_name = config["database"]["path_env"]
    return os.environ.get(env_name) or config["database"]["default_path"]


def log_level() -> str:
    config = load_config()
    env_name = config["logging"]["level_env"]
    return os.environ.get(env_name) or config["logging"]["default_level"]
