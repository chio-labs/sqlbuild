from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.virtual.executor._helpers.rollback import read_rollback_physical_relations
from sqlbuild.virtual.executor._helpers.seeding import read_seed_physical_relations
from sqlbuild.virtual.executor.models import RollbackResolution
from sqlbuild.virtual.state.models import PhysicalRelationRecord
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    MissingRollbackSeedRelationTestCase,
    SeedPhysicalRelationLookupTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor._helpers.helpers import (
    SeedPhysicalRelationTestBackend,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedPhysicalRelationLookupTestCase(
            description="available seed relations are returned by seed name",
            seed_version_hashes={"orders": "orders-hash", "customers": "customers-hash"},
            available_seed_names=("customers", "orders"),
            expected_seed_names=("customers", "orders"),
        ),
        SeedPhysicalRelationLookupTestCase(
            description="missing seed relations are omitted for caller policy",
            seed_version_hashes={"orders": "orders-hash", "customers": "customers-hash"},
            available_seed_names=("orders",),
            expected_seed_names=("orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seed_version_hashes_when_reading_relations_then_available_records_are_returned(
    test_case: SeedPhysicalRelationLookupTestCase,
) -> None:
    backend: SeedPhysicalRelationTestBackend = SeedPhysicalRelationTestBackend(
        available_seed_names=test_case.available_seed_names
    )

    result: dict[str, PhysicalRelationRecord] = read_seed_physical_relations(
        backend=backend,
        state_connection=object(),
        schema="state",
        seed_version_hashes=test_case.seed_version_hashes,
    )

    assert tuple(sorted(result)) == test_case.expected_seed_names


@pytest.mark.parametrize(
    "test_case",
    [
        MissingRollbackSeedRelationTestCase(
            description="rollback rejects a checkpoint with a missing seed relation",
            final_seed_hashes={"orders": "orders-hash"},
            expected_error_fragment=(
                "checkpoint references missing physical relation for seed 'orders'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_checkpoint_seed_relation_when_reading_rollback_then_it_raises(
    test_case: MissingRollbackSeedRelationTestCase,
) -> None:
    backend: SeedPhysicalRelationTestBackend = SeedPhysicalRelationTestBackend(
        available_seed_names=()
    )
    resolution: RollbackResolution = RollbackResolution(
        final_version_hashes={},
        final_seed_hashes=test_case.final_seed_hashes,
        is_partial_scope=False,
        status=VirtualEnvironmentStatus.FINALIZED,
        rolled_back_model_names=(),
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        read_rollback_physical_relations(
            backend=backend,
            state_connection=object(),
            schema="state",
            checkpoint_id="checkpoint-1",
            resolution=resolution,
        )
