"""Rules configuration loading entrypoint."""

from pathlib import Path

from sqlbuild._native import load_rules_config as _load_rules_config
from sqlbuild.rule_engine.models import RulesConfig


def load_rules_config(*, project_dir: Path) -> RulesConfig:
    """Load strict rules configuration from a SQLBuild project."""

    return _load_rules_config(project_dir=project_dir.resolve())
