"""Project specification constants."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SeedCsvSettings

DEFAULT_SEED_CSV_SETTINGS: SeedCsvSettings = SeedCsvSettings()
CHANGES_ONLY_SETTING_OVERRIDE_KEY: str = "changes_only"
CURSOR_POLICY_DISABLED: str = "disabled"
ZERO_DAY_CURSOR_DURATION: str = "0d"
TIME_TRAVEL_RETENTION_MATERIALIZATIONS: tuple[str, ...] = (
    "table",
    "incremental",
    "snapshot",
)
