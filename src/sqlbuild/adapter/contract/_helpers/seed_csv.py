"""Shared seed CSV null handling."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SeedCsvSettings

_DEFAULT_NULL_VALUE: str = ""


def get_seed_csv_null_values(csv_settings: SeedCsvSettings) -> tuple[str, ...]:
    """Return global CSV values that represent SQL nulls."""

    null_values: list[str] = []
    if csv_settings.keep_default_na is not False:
        null_values.append(_DEFAULT_NULL_VALUE)
    if isinstance(csv_settings.na_values, tuple):
        null_values.extend(str(value) for value in csv_settings.na_values)
    return tuple(dict.fromkeys(null_values))


def normalize_seed_csv_value(
    *, value: str | None, column_name: str, csv_settings: SeedCsvSettings
) -> str | None:
    """Convert configured CSV null representations to None."""

    if value is None:
        return None
    if value in get_seed_csv_null_values(csv_settings):
        return None
    if isinstance(csv_settings.na_values, dict):
        column_null_values: tuple[object, ...] = csv_settings.na_values.get(column_name, ())
        if value in {str(item) for item in column_null_values}:
            return None
    return value
