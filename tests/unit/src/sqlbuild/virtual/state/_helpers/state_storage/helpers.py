"""Helpers for conditional publication validation tests."""

from sqlbuild.virtual.state._helpers.state_storage.validation import (
    validate_conditional_virtual_environment_publication,
)
from tests.unit.src.sqlbuild.virtual.state._helpers.helpers import FakeStateBackend
from tests.unit.src.sqlbuild.virtual.state._helpers.state_storage._test_types import (
    ConditionalPublicationValidationTestCase,
)


def validate_case(test_case: ConditionalPublicationValidationTestCase) -> bool:
    validate_conditional_virtual_environment_publication(
        record=test_case.record,
        refs_by_node_type=test_case.refs_by_node_type,
        checkpoint=test_case.checkpoint,
        checkpoint_refs=test_case.checkpoint_refs,
        checkpoint_function_refs=test_case.checkpoint_function_refs,
        checkpoint_seed_refs=test_case.checkpoint_seed_refs,
    )
    return True


def publish_fake_case(test_case: ConditionalPublicationValidationTestCase) -> bool:
    return FakeStateBackend(
        acquire_result=True
    ).upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        connection=object(),
        schema="state",
        record=test_case.record,
        refs_by_node_type=test_case.refs_by_node_type,
        leases=(),
        checkpoint=test_case.checkpoint,
        checkpoint_refs=test_case.checkpoint_refs,
        checkpoint_function_refs=test_case.checkpoint_function_refs,
        checkpoint_seed_refs=test_case.checkpoint_seed_refs,
    )
