"""Load pipeline configuration from YAML."""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "screeners.yaml"


def load_config(path: Path | None = None) -> dict:
    config_path = path or CONFIG_PATH
    with open(config_path) as f:
        return yaml.safe_load(f)
