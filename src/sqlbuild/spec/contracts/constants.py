"""Project specification constants."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SeedCsvSettings

DEFAULT_SEED_CSV_SETTINGS: SeedCsvSettings = SeedCsvSettings()
ZERO_DAY_CURSOR_DURATION: str = "0d"
DEFAULT_DIFF_MAX_FULL_ROWS: int = 10_000_000
