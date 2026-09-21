"""Public lint entry for fixture-null candidate discovery."""

from pathlib import Path

from sqlbuild.lint._helpers.fixture_null_candidates import (
    has_fixture_typed_null_candidates as _has_fixture_typed_null_candidates,
)


def has_fixture_typed_null_candidates(*, project_dir: Path) -> bool:
    """Return whether source files may contain safe fixture-null autofixes."""

    return _has_fixture_typed_null_candidates(project_dir=project_dir)
