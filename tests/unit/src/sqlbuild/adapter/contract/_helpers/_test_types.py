from dataclasses import dataclass

from sqlbuild.spec.contracts.models import SeedCsvSettings


@dataclass(frozen=True)
class NormalizeSeedCsvValueTestCase:
    """One seed CSV null-normalization case."""

    description: str
    value: str | None
    column_name: str
    csv_settings: SeedCsvSettings
    expected_value: str | None
