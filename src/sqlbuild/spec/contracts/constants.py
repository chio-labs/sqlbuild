"""Project specification constants."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SeedCsvSettings

LOADER_SCHEMA_TABLE_PART_COUNT: int = 2
LOADER_QUALIFIED_TABLE_PART_COUNT: int = 3
DEFAULT_SEED_CSV_SETTINGS: SeedCsvSettings = SeedCsvSettings()
CHANGES_ONLY_SETTING_OVERRIDE_KEY: str = "changes_only"
CURSOR_POLICY_DISABLED: str = "disabled"
ZERO_DAY_CURSOR_DURATION: str = "0d"
EFFECTIVE_BATCH_SIZE_TOKEN: str = "effective"
TIME_TRAVEL_RETENTION_MATERIALIZATIONS: tuple[str, ...] = (
    "table",
    "incremental",
    "snapshot",
)
