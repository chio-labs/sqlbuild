"""Translate safe Dagster identifiers into opaque SQLBuild invocation context."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

_MAX_IDENTIFIER_JSON_BYTES: int = 1_024


def dagster_invocation_context(context: Any) -> dict[str, object]:
    """Return bounded, non-sensitive identifiers for subprocess correlation."""

    integration: dict[str, object] = {"name": "dagster"}
    run_id: str | None = _string_attribute(source=context, name="run_id")
    if run_id is not None:
        integration["run_id"] = run_id
    job_name: str | None = _string_attribute(source=context, name="job_name")
    if job_name is not None:
        integration["job_name"] = job_name
    retry_number: int | None = _integer_attribute(source=context, name="retry_number")
    if retry_number is not None:
        integration["retry_number"] = retry_number
    step_key: str | None = _step_key(context=context)
    if step_key is not None:
        integration["step_key"] = step_key
    if _boolean_attribute(source=context, name="has_partition_key") is True:
        partition_key: str | None = _string_attribute(source=context, name="partition_key")
        if partition_key is not None:
            integration["partition_key"] = partition_key
    return {"integration": integration}


def _step_key(*, context: Any) -> str | None:
    direct: object | None = _attribute(source=context, name="step_key")
    bounded_direct: str | None = _bounded_identifier(direct)
    if bounded_direct is not None:
        return bounded_direct
    handle: object | None = _attribute(source=context, name="op_handle")
    formatter: object | None = _attribute(source=handle, name="to_string")
    if callable(formatter):
        value: object = cast(Callable[[], object], formatter)()
        return _bounded_identifier(value)
    return None


def _string_attribute(*, source: Any, name: str) -> str | None:
    return _bounded_identifier(_attribute(source=source, name=name))


def _bounded_identifier(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    encoded: bytes = json.dumps(value, ensure_ascii=True).encode("utf-8")
    return value if len(encoded) <= _MAX_IDENTIFIER_JSON_BYTES else None


def _integer_attribute(*, source: Any, name: str) -> int | None:
    value: object | None = _attribute(source=source, name=name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _boolean_attribute(*, source: Any, name: str) -> bool | None:
    value: object | None = _attribute(source=source, name=name)
    return value if isinstance(value, bool) else None


def _attribute(*, source: Any, name: str) -> object | None:
    if source is None:
        return None
    try:
        return getattr(source, name, None)
    except BaseException:
        return None
