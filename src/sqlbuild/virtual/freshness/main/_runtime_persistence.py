"""Public source freshness runtime persistence entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.virtual.freshness._helpers.runtime import (
    persist_virtual_environment_source_freshness as _persist_virtual_environment_source_freshness,
)
from sqlbuild.virtual.freshness.models import SourceFreshnessRuntimeResult


def persist_virtual_environment_source_freshness(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
    result: SourceFreshnessRuntimeResult,
) -> None:
    """Persist the latest observed freshness records for a virtual environment."""

    _ = _persist_virtual_environment_source_freshness(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
        result=result,
    )
