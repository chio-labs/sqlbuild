from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.compile.types import CompiledProjectView


@dataclass(frozen=True)
class HostPayloadFactsTestCase:
    """A compiled project written as a host payload, and the facts that must not be empty."""

    description: str
    project_files: dict[str, str]
    payload_source: Callable[[CompiledProjectView], CompiledProjectView]
    expected_populated_facts: tuple[str, ...]


@dataclass(frozen=True)
class HostPayloadLazyReadTestCase:
    """A rule reading one fact per model, and the facts its host must leave encoded."""

    description: str
    project_files: dict[str, str]
    expected_enforced: tuple[bool, ...]
    expected_encoded_model_facts: frozenset[str]
    expected_encoded_project_facts: frozenset[str]
