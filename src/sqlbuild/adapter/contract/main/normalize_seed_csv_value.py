"""Public seed CSV normalization entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.contract._helpers.seed_csv import normalize_seed_csv_value as _normalize
from sqlbuild.spec.contracts.models import SeedCsvSettings


def normalize_seed_csv_value(
    *, value: str | None, column_name: str, csv_settings: SeedCsvSettings
) -> str | None:
    """Convert configured CSV null representations to None."""

    return _normalize(value=value, column_name=column_name, csv_settings=csv_settings)
