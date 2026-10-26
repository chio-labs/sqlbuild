from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRuleTestsTestCase:
    description: str
    import_mode: str
    rule_test_path: str
    expected_summary: str = "2 passed"
