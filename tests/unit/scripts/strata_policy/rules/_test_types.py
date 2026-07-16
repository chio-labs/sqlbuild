from dataclasses import dataclass

from strata import RuleFile


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    files: tuple[RuleFile, ...] = ()
    scope: str = "root"
    scope_root: str | None = "src/sqlbuild"
