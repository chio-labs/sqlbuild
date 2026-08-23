"""Kata catalogue construction entrypoint."""

from pathlib import Path

from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue as _build_catalogue
from sqlbuild.kata_engine.models import KataConfig, KataRule


def build_catalogue(*, config: KataConfig, project_dir: Path) -> tuple[KataRule, ...]:
    """Build the validated built-in and custom kata catalogue."""

    return _build_catalogue(config=config, project_dir=project_dir)
