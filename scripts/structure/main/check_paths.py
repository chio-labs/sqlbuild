"""Run structure convention checks for selected paths."""

from pathlib import Path

from scripts.structure._helpers.convention_checks import (
    collect_violations,
)
from scripts.structure.models import Violation


def check_paths(*, paths: list[Path], repo_root: Path | None = None) -> list[Violation]:
    """Run structure convention checks for the provided paths."""

    return collect_violations(paths=paths, repo_root=repo_root)
