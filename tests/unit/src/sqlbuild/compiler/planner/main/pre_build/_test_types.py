from dataclasses import dataclass

from sqlbuild.compiler.migrations.types import MigrationCompatibility, MigrationDecision


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
