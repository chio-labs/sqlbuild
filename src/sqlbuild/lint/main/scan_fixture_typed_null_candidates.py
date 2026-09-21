"""Public lint entry for selected fixture-null candidate discovery."""

from pathlib import Path

from sqlbuild.lint._helpers.fixture_null_candidates import (
    scan_fixture_typed_null_candidates as _scan_fixture_typed_null_candidates,
)
from sqlbuild.lint.models import FixtureNullCandidateScan


def scan_fixture_typed_null_candidates(
    *, project_dir: Path, selected_paths: frozenset[Path] | None = None
) -> FixtureNullCandidateScan:
    """Return selected SQL-test fixture-null candidates and referenced model names."""

    return _scan_fixture_typed_null_candidates(
        project_dir=project_dir,
        selected_paths=selected_paths,
    )
