"""Kata configuration loading entrypoint."""

from pathlib import Path

from sqlbuild.kata_engine._helpers.engine.config import load_kata_config as _load_kata_config
from sqlbuild.kata_engine.models import KataConfig


def load_kata_config(*, project_dir: Path) -> KataConfig:
    """Load strict kata configuration from a SQLBuild project."""

    return _load_kata_config(project_dir)
