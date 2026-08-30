"""State schema validation helper functions."""

from __future__ import annotations

from sqlbuild.virtual.state.constants import STATE_TABLES
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import (
    StateSchemaValidationIssue,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import (
    StateColumnType,
    StateSchemaValidationIssueKind,
    StateTypeMatcher,
    VirtualEnvironmentStatus,
)

_MODEL_NODE_TYPE: str = "model"
_SEED_NODE_TYPE: str = "seed"
_FUNCTION_NODE_TYPES: tuple[str, ...] = ("udf", "table_fn")


def build_validation_result(
    *,
    existing_tables: set[str],
    columns_by_table: dict[str, dict[str, str]],
    expected_columns: dict[str, dict[str, StateColumnType]],
    type_matches: StateTypeMatcher,
    expected_indexes: dict[str, dict[str, tuple[str, ...]]] | None = None,
    existing_indexes_by_table: dict[str, set[str]] | None = None,
) -> StateSchemaValidationResult:
    """Build validation issues for required tables and columns."""

    issues: list[StateSchemaValidationIssue] = []
    table_name: str
    for table_name in STATE_TABLES:
        if table_name not in existing_tables:
            issues.append(
                StateSchemaValidationIssue(
                    kind=StateSchemaValidationIssueKind.MISSING_TABLE,
                    table_name=table_name,
                    message=f"Missing state table: {table_name}",
                )
            )
            continue
        column_name: str
        expected_type: StateColumnType
        actual_columns: dict[str, str] = columns_by_table.get(table_name, {})
        for column_name, expected_type in expected_columns[table_name].items():
            actual_type: str | None = actual_columns.get(column_name)
            if actual_type is None:
                issues.append(
                    StateSchemaValidationIssue(
                        kind=StateSchemaValidationIssueKind.MISSING_COLUMN,
                        table_name=table_name,
                        column_name=column_name,
                        message=f"Missing state column: {table_name}.{column_name}",
                    )
                )
                continue
            if not type_matches(actual_type=actual_type, expected_type=expected_type):
                issues.append(
                    StateSchemaValidationIssue(
                        kind=StateSchemaValidationIssueKind.WRONG_TYPE,
                        table_name=table_name,
                        column_name=column_name,
                        message=(
                            f"Wrong state column type: {table_name}.{column_name} "
                            f"expected {expected_type.value}, got {actual_type}"
                        ),
                    )
                )
        if expected_indexes is not None:
            actual_indexes: set[str] = (existing_indexes_by_table or {}).get(table_name, set())
            index_name: str
            for index_name in expected_indexes.get(table_name, {}):
                if index_name not in actual_indexes:
                    issues.append(
                        StateSchemaValidationIssue(
                            kind=StateSchemaValidationIssueKind.MISSING_INDEX,
                            table_name=table_name,
                            message=f"Missing state index: {table_name}.{index_name}",
                        )
                    )
    return StateSchemaValidationResult(issues=tuple(issues))


def validate_conditional_virtual_environment_publication(
    *,
    record: VirtualEnvironmentRecord,
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    checkpoint: VirtualEnvironmentCheckpointRecord | None,
    checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
    checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
) -> None:
    """Validate one conditional environment/ref/checkpoint publication before writes begin."""

    has_checkpoint_payload: bool = checkpoint is not None or bool(
        checkpoint_refs or checkpoint_function_refs or checkpoint_seed_refs
    )
    if record.status == VirtualEnvironmentStatus.FINALIZED and checkpoint is None:
        raise StateBackendConfigError(
            "Finalized conditional virtual environment publication requires a checkpoint"
        )
    if record.status == VirtualEnvironmentStatus.ACTIVE and has_checkpoint_payload:
        raise StateBackendConfigError(
            "Active conditional virtual environment publication forbids checkpoint payloads"
        )
    if checkpoint is None:
        if has_checkpoint_payload:
            raise StateBackendConfigError("Checkpoint refs require a checkpoint record")
        _validate_current_ref_groups(record=record, refs_by_node_type=refs_by_node_type)
        return
    if checkpoint.virtual_environment_name != record.virtual_environment_name:
        raise StateBackendConfigError(
            "Checkpoint virtual_environment_name must match the published environment"
        )

    _validate_current_ref_groups(record=record, refs_by_node_type=refs_by_node_type)
    checkpoint_id: str = checkpoint.checkpoint_id
    _validate_checkpoint_ids(
        checkpoint_id=checkpoint_id,
        refs=checkpoint_refs,
        function_refs=checkpoint_function_refs,
        seed_refs=checkpoint_seed_refs,
    )
    _validate_exact_ref_pairs(
        label="model",
        current_pairs=tuple(
            (ref.node_name, ref.version_hash) for ref in refs_by_node_type.get(_MODEL_NODE_TYPE, ())
        ),
        checkpoint_pairs=tuple((ref.model_name, ref.version_hash) for ref in checkpoint_refs),
    )
    _validate_exact_ref_pairs(
        label="function",
        current_pairs=_current_function_pairs(refs_by_node_type),
        checkpoint_pairs=tuple(
            (ref.function_name, ref.version_hash) for ref in checkpoint_function_refs
        ),
    )
    _validate_exact_ref_pairs(
        label="seed",
        current_pairs=tuple(
            (ref.node_name, ref.version_hash) for ref in refs_by_node_type.get(_SEED_NODE_TYPE, ())
        ),
        checkpoint_pairs=tuple((ref.seed_name, ref.version_hash) for ref in checkpoint_seed_refs),
    )


def _validate_current_ref_groups(
    *,
    record: VirtualEnvironmentRecord,
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
) -> None:
    node_type: str
    refs: tuple[VirtualEnvironmentNodeRefRecord, ...]
    for node_type, refs in refs_by_node_type.items():
        identities: list[str] = []
        ref: VirtualEnvironmentNodeRefRecord
        for ref in refs:
            if ref.virtual_environment_name != record.virtual_environment_name:
                raise StateBackendConfigError(
                    "Published ref virtual_environment_name must match the environment record"
                )
            if ref.node_type != node_type:
                raise StateBackendConfigError("Published ref node_type must match its ref group")
            identities.append(ref.node_name)
        if len(identities) != len(set(identities)):
            raise StateBackendConfigError(
                f"Published {node_type} refs contain duplicate identities"
            )


def _current_function_pairs(
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    node_type: str
    for node_type in _FUNCTION_NODE_TYPES:
        ref: VirtualEnvironmentNodeRefRecord
        for ref in refs_by_node_type.get(node_type, ()):
            pairs.append((ref.node_name, ref.version_hash))
    return tuple(pairs)


def _validate_checkpoint_ids(
    *,
    checkpoint_id: str,
    refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
    function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
    seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
) -> None:
    actual_ids: tuple[str, ...] = tuple(
        ref.checkpoint_id for ref in (*refs, *function_refs, *seed_refs)
    )
    if any(actual_id != checkpoint_id for actual_id in actual_ids):
        raise StateBackendConfigError(
            "Every checkpoint ref checkpoint_id must match the checkpoint record"
        )


def _validate_exact_ref_pairs(
    *,
    label: str,
    current_pairs: tuple[tuple[str, str], ...],
    checkpoint_pairs: tuple[tuple[str, str], ...],
) -> None:
    current_identities: tuple[str, ...] = tuple(identity for identity, _ in current_pairs)
    checkpoint_identities: tuple[str, ...] = tuple(identity for identity, _ in checkpoint_pairs)
    if len(checkpoint_identities) != len(set(checkpoint_identities)):
        raise StateBackendConfigError(f"Checkpoint {label} refs contain duplicate identities")
    if len(current_identities) != len(set(current_identities)):
        raise StateBackendConfigError(f"Published {label} refs contain duplicate identities")
    if set(current_pairs) != set(checkpoint_pairs):
        raise StateBackendConfigError(
            f"Checkpoint {label} refs must exactly match the published {label} refs"
        )
