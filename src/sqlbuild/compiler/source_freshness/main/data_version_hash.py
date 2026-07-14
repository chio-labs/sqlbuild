"""Public shared source freshness data-version hash entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.source_freshness.helpers.state import (
    source_freshness_data_version_hash as _source_freshness_data_version_hash,
)
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind


def source_freshness_data_version_hash(
    *,
    source_name: str,
    strategy: SourceFreshnessStrategy | str,
    value_kind: SourceFreshnessValueKind | str,
    data_version: str,
) -> str:
    """Hash the stable source freshness identity used as a graph input."""

    return _source_freshness_data_version_hash(
        source_name=source_name,
        strategy=strategy,
        value_kind=value_kind,
        data_version=data_version,
    )
