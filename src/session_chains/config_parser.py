import yaml

from pathlib import Path


def parse_config(config: Path):
    with open(config, "r") as f:
        yaml_data = yaml.safe_load(f)
    return yaml_data
