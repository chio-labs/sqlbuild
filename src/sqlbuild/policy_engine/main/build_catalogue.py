"""Policy catalogue construction entrypoint."""

from pathlib import Path

from sqlbuild.policy_engine._helpers.engine.catalogue import build_catalogue as _build_catalogue
from sqlbuild.policy_engine.models import PolicyConfig, PolicyRule


def build_catalogue(*, config: PolicyConfig, project_dir: Path) -> tuple[PolicyRule, ...]:
    """Build the validated built-in and custom policy catalogue."""

    return _build_catalogue(config=config, project_dir=project_dir)
