"""Policy configuration loading entrypoint."""

from pathlib import Path

from sqlbuild.policy_engine._helpers.engine.config import load_policy_config as _load_policy_config
from sqlbuild.policy_engine.models import PolicyConfig


def load_policy_config(*, project_dir: Path) -> PolicyConfig:
    """Load strict policy configuration from a SQLBuild project."""

    return _load_policy_config(project_dir)
