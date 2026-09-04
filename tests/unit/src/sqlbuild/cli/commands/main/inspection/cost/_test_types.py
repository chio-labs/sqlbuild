from dataclasses import dataclass


@dataclass(frozen=True)
class CostCommandTestCase:
    description: str
    expected_exit_code: int = 0
    expected_run_ids: tuple[str, ...] = ()
    expected_error_fragment: str = ""
    expected_schema_version: int = 1


@dataclass(frozen=True)
class CostRelativeSinceTestCase:
    description: str
    value: str
    expected_seconds: int | None = None
    expected_error_fragment: str | None = None
