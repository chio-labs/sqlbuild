from dataclasses import dataclass

from fensu import RuleFile


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    files: tuple[RuleFile, ...] = ()
    scope: str = "root"
    scope_root: str | None = "src/sqlbuild"


@dataclass(frozen=True)
class NativeLinesTestCase:
    description: str
    source: str
    expected_lines: tuple[int, ...]


@dataclass(frozen=True)
class NativePatchTestCase:
    description: str
    source: str
    expected_fault_count: int
    budgets: tuple[str, ...] = ()
