from dataclasses import dataclass


@dataclass(frozen=True)
class LoadSelectionTestCase:
    description: str
    select: tuple[str, ...]
    expected_entry_names: tuple[str, ...]
    expected_loader_node_flags: tuple[bool, ...]
