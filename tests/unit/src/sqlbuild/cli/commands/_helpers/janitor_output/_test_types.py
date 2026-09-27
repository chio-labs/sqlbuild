from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorCompletionTestCase:
    description: str
    archived: int
    deleted: int
    pruned_direct_state: int
    expected_output: str
