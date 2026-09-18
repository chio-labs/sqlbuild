"""Public diff invocation configuration entrypoints."""

from sqlbuild.adapter.contract.models import RowDiffTolerances
from sqlbuild.executor.diff._helpers.config import (
    parse_cli_tolerance_overrides as _parse_cli_tolerance_overrides,
)


def parse_cli_tolerance_overrides(*, values: tuple[str, ...]) -> RowDiffTolerances:
    """Parse repeated invocation-level per-column tolerance rules."""

    return _parse_cli_tolerance_overrides(values=values)
