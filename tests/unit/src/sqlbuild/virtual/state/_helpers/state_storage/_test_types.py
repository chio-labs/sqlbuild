"""Test types for conditional virtual publication validation."""

from dataclasses import dataclass

from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)


@dataclass(frozen=True)
class ConditionalPublicationValidationTestCase:
    """One conditional publication payload and its expected validation result."""

    description: str
    record: VirtualEnvironmentRecord
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]]
    checkpoint: VirtualEnvironmentCheckpointRecord | None
    checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]
    checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]
    expected_valid: bool = True
    expected_error_fragment: str | None = None
