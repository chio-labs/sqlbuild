"""Rules catalogue construction entrypoint."""

from pathlib import Path

from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue as _build_catalogue
from sqlbuild.rule_engine.models import Rule, RulesConfig


def build_catalogue(*, config: RulesConfig, project_dir: Path) -> tuple[Rule, ...]:
    """Build the validated built-in and custom rules catalogue."""

    return _build_catalogue(config=config, project_dir=project_dir)
