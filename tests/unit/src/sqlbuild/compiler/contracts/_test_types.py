from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContractValidationTestCase:
    description: str
    declared_columns: tuple[tuple[str, str | None], ...]
    inferred_columns: tuple[tuple[str, str | None], ...] | None
    type_enforcement: bool | None
    expected_codes: tuple[str, ...]
    expected_severities: tuple[str, ...]
    expected_messages: tuple[str, ...]
