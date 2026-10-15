"""Project specification constants."""

from __future__ import annotations

from sqlbuild._native import SeedCsvSettings

DEFAULT_SEED_CSV_SETTINGS: SeedCsvSettings = SeedCsvSettings()
ZERO_DAY_CURSOR_DURATION: str = "0d"
