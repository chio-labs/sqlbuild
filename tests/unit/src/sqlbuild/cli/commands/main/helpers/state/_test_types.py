from dataclasses import dataclass


@dataclass(frozen=True)
class CheckpointOutputTestCase:
    description: str
    expected_rendered: str


@dataclass(frozen=True)
class CheckpointColorOutputTestCase:
    description: str
    expected_fragments: tuple[str, ...]
