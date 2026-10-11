from dataclasses import dataclass


@dataclass(frozen=True)
class NativeRulesRequestTestCase:
    """A compile of the rules fixture: request rows built natively and cache use."""

    description: str
    expected_built_rows: tuple[int, int, int]
    expected_cold_cache: tuple[int, int]
    expected_warm_cache: tuple[int, int]
    expected_edited_cache: tuple[int, int]


@dataclass(frozen=True)
class NativeTypeProofTestCase:
    """A type-proof findings for a contract with matching and mismatched casts."""

    description: str
    expected_findings: tuple[tuple[str, str, int | None, int | None, str], ...]
    expected_built_rows: tuple[int, int, int]


@dataclass(frozen=True)
class StructPassthroughTestCase:
    """A STRUCT passthrough whose type proof asks the adapter's `types_equal` callback."""

    description: str
    declared_type: str
    expected_exit_code: int
    expected_codes: tuple[str, ...]
