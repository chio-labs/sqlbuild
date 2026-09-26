from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorCompletionTestCase:
    description: str
    archived: int
    deleted: int
    deleted_state_backups: int
    deleted_checkpoints: int
    pruned_direct_state: int
    expected_output: str
