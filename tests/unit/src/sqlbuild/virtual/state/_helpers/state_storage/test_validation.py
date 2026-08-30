"""Conditional virtual publication validation contract tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus
from tests.unit.src.sqlbuild.virtual.state._helpers.state_storage._test_types import (
    ConditionalPublicationValidationTestCase,
)
from tests.unit.src.sqlbuild.virtual.state._helpers.state_storage.helpers import (
    publish_fake_case,
    validate_case,
)

_ENVIRONMENT: str = "dev"
_CHECKPOINT_ID: str = "checkpoint-1"
_FINALIZED_RECORD: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
    virtual_environment_name=_ENVIRONMENT,
    status=VirtualEnvironmentStatus.FINALIZED,
)
_ACTIVE_RECORD: VirtualEnvironmentRecord = replace(
    _FINALIZED_RECORD,
    status=VirtualEnvironmentStatus.ACTIVE,
)
_REF_GROUPS: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]] = {
    "model": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "model", "orders", "model-v1"),),
    "udf": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "udf", "normalize", "function-v1"),),
    "seed": (VirtualEnvironmentNodeRefRecord(_ENVIRONMENT, "seed", "countries", "seed-v1"),),
}
_CHECKPOINT: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
    checkpoint_id=_CHECKPOINT_ID,
    virtual_environment_name=_ENVIRONMENT,
)
_MODEL_REFS: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (
    VirtualEnvironmentCheckpointModelRefRecord(_CHECKPOINT_ID, "orders", "model-v1"),
)
_FUNCTION_REFS: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (
    VirtualEnvironmentCheckpointFunctionRefRecord(_CHECKPOINT_ID, "normalize", "function-v1"),
)
_SEED_REFS: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (
    VirtualEnvironmentCheckpointSeedRefRecord(_CHECKPOINT_ID, "countries", "seed-v1"),
)

_SUCCESS_CASES: tuple[ConditionalPublicationValidationTestCase, ...] = (
    ConditionalPublicationValidationTestCase(
        description="finalized exact checkpoint payload succeeds",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
    ),
    ConditionalPublicationValidationTestCase(
        description="active publication without checkpoint succeeds",
        record=_ACTIVE_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=None,
        checkpoint_refs=(),
        checkpoint_function_refs=(),
        checkpoint_seed_refs=(),
    ),
)

_ERROR_CASES: tuple[ConditionalPublicationValidationTestCase, ...] = (
    ConditionalPublicationValidationTestCase(
        description="finalized publication requires checkpoint",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=None,
        checkpoint_refs=(),
        checkpoint_function_refs=(),
        checkpoint_seed_refs=(),
        expected_error_fragment="requires a checkpoint",
    ),
    ConditionalPublicationValidationTestCase(
        description="active publication forbids complete checkpoint payload",
        record=_ACTIVE_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="requires finalized virtual environment status",
    ),
    ConditionalPublicationValidationTestCase(
        description="finalizing publication forbids complete checkpoint payload",
        record=replace(_FINALIZED_RECORD, status=VirtualEnvironmentStatus.FINALIZING),
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="requires finalized virtual environment status",
    ),
    ConditionalPublicationValidationTestCase(
        description="detached publication forbids complete checkpoint payload",
        record=replace(_FINALIZED_RECORD, status=VirtualEnvironmentStatus.DETACHED),
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="requires finalized virtual environment status",
    ),
    ConditionalPublicationValidationTestCase(
        description="failed publication forbids complete checkpoint payload",
        record=replace(_FINALIZED_RECORD, status=VirtualEnvironmentStatus.FAILED),
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="requires finalized virtual environment status",
    ),
    ConditionalPublicationValidationTestCase(
        description="checkpoint environment must match",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=replace(_CHECKPOINT, virtual_environment_name="other"),
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="must match the published environment",
    ),
    ConditionalPublicationValidationTestCase(
        description="model checkpoint id must match",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=(replace(_MODEL_REFS[0], checkpoint_id="other"),),
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="checkpoint_id must match",
    ),
    ConditionalPublicationValidationTestCase(
        description="function checkpoint id must match",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=(replace(_FUNCTION_REFS[0], checkpoint_id="other"),),
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="checkpoint_id must match",
    ),
    ConditionalPublicationValidationTestCase(
        description="seed checkpoint id must match",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=(replace(_SEED_REFS[0], checkpoint_id="other"),),
        expected_error_fragment="checkpoint_id must match",
    ),
    ConditionalPublicationValidationTestCase(
        description="model version must correspond exactly",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=(replace(_MODEL_REFS[0], version_hash="other"),),
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="model refs must exactly match",
    ),
    ConditionalPublicationValidationTestCase(
        description="function omission is rejected",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=(),
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="function refs must exactly match",
    ),
    ConditionalPublicationValidationTestCase(
        description="seed extra ref is rejected",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=(
            *_SEED_REFS,
            VirtualEnvironmentCheckpointSeedRefRecord(_CHECKPOINT_ID, "extra", "seed-v2"),
        ),
        expected_error_fragment="seed refs must exactly match",
    ),
    ConditionalPublicationValidationTestCase(
        description="checkpoint duplicate identity is rejected",
        record=_FINALIZED_RECORD,
        refs_by_node_type=_REF_GROUPS,
        checkpoint=_CHECKPOINT,
        checkpoint_refs=(*_MODEL_REFS, *_MODEL_REFS),
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="duplicate identities",
    ),
    ConditionalPublicationValidationTestCase(
        description="published duplicate identity is rejected",
        record=_FINALIZED_RECORD,
        refs_by_node_type={**_REF_GROUPS, "model": (*_REF_GROUPS["model"], *_REF_GROUPS["model"])},
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="duplicate identities",
    ),
    ConditionalPublicationValidationTestCase(
        description="published ref environment must match",
        record=_FINALIZED_RECORD,
        refs_by_node_type={
            **_REF_GROUPS,
            "model": (replace(_REF_GROUPS["model"][0], virtual_environment_name="other"),),
        },
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="ref virtual_environment_name must match",
    ),
    ConditionalPublicationValidationTestCase(
        description="published ref node type must match group",
        record=_FINALIZED_RECORD,
        refs_by_node_type={
            **_REF_GROUPS,
            "model": (replace(_REF_GROUPS["model"][0], node_type="seed"),),
        },
        checkpoint=_CHECKPOINT,
        checkpoint_refs=_MODEL_REFS,
        checkpoint_function_refs=_FUNCTION_REFS,
        checkpoint_seed_refs=_SEED_REFS,
        expected_error_fragment="node_type must match",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [ConditionalPublicationValidationTestCase(**case.__dict__) for case in _SUCCESS_CASES],
    ids=lambda case: case.description,
)
def test_given_valid_conditional_publication_when_validating_then_succeeds(
    test_case: ConditionalPublicationValidationTestCase,
) -> None:
    assert validate_case(test_case) is test_case.expected_valid
    assert publish_fake_case(test_case) is test_case.expected_valid


@pytest.mark.parametrize(
    "test_case",
    [ConditionalPublicationValidationTestCase(**case.__dict__) for case in _ERROR_CASES],
    ids=lambda case: case.description,
)
def test_given_invalid_conditional_publication_when_validating_then_raises_structured_error(
    test_case: ConditionalPublicationValidationTestCase,
) -> None:
    with pytest.raises(StateBackendConfigError, match=test_case.expected_error_fragment or ""):
        validate_case(test_case)

    with pytest.raises(StateBackendConfigError, match=test_case.expected_error_fragment or ""):
        publish_fake_case(test_case)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
