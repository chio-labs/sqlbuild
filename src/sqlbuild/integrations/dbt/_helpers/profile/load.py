"""Parse dbt project and profile YAML files with PyYAML."""

from __future__ import annotations

from pathlib import Path

import yaml
from yaml import YAMLError

from sqlbuild.integrations.dbt.exceptions import DbtProfileError


def load_dbt_yaml(*, file_path: Path) -> object:
    """Return the YAML document of one dbt config file."""

    try:
        return yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except YAMLError as error:
        raise DbtProfileError(f"{file_path} contains invalid YAML: {error}") from error
