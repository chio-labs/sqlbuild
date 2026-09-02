"""Safe BigQuery statement telemetry extraction."""

from typing import Any


def affected_rows(*, job: Any) -> int | None:
    """Return BigQuery's reliable nonnegative DML affected-row count."""

    value: object | None = getattr(job, "num_dml_affected_rows", None)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
