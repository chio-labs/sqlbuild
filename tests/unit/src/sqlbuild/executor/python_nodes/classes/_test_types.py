"""Test case types for the run-time relation guard."""

from dataclasses import dataclass, field

from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class RuntimeRelationGuardTestCase:
    """SQL a Python node sends, and the hard-coded-name warnings it produces."""

    description: str
    statements: tuple[str, ...]
    expected_warning_fragments: tuple[str, ...]
    resolved_refs: tuple[SqlResourceRef, ...] = field(default_factory=tuple)
    own_refs: frozenset[SqlResourceRef] = frozenset()
