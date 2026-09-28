from dataclasses import dataclass

from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
)


@dataclass(frozen=True)
class MigrationDecisionStyleTestCase:
    description: str
    decision: MigrationDecision
    compatibility: MigrationCompatibility
    findings: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class MigrationPlainTextTestCase:
    description: str
    decision: MigrationDecision
    expected_text: str


@dataclass(frozen=True)
class ColumnMigrationPlainTextTestCase:
    description: str
    entries: tuple[tuple[str, str, str, ColumnMigrationDecision, MigrationDiscovery], ...]
    expected_text: str


@dataclass(frozen=True)
class ColumnMigrationStyleTestCase:
    description: str
    decision: ColumnMigrationDecision
    expected_fragment: str
