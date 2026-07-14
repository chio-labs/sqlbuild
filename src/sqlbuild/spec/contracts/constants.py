"""Project specification constants."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SeedCsvSettings

DEFAULT_SEED_CSV_SETTINGS: SeedCsvSettings = SeedCsvSettings()
FORCE_SETTING_OVERRIDE_KEY: str = "force"
