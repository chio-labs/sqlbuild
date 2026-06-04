from dataclasses import dataclass


@dataclass(frozen=True)
class DirectSourceFreshnessPlanOutputTestCase:
    description: str
    changes_only: bool
    expected_has_source_freshness: bool
