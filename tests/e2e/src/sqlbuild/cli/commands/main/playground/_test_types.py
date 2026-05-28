from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualPlaygroundLifecycleTestCase:
    description: str
    project_name: str
    expected_build_fragments: tuple[str, ...]
    expected_test_fragments: tuple[str, ...]
    expected_audit_fragments: tuple[str, ...]
    expected_scenario_fragments: tuple[str, ...]
    expected_branch_fragments: tuple[str, ...]
    expected_diff_fragments: tuple[str, ...]
    expected_promote_fragments: tuple[str, ...]
