from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledObjectKey,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.models import DirectModelVersionIdentities
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import build_compiled_function
from tests.unit.src.sqlbuild.compiler.planner.main.identity._test_types import (
    FunctionReturnContractIdentityTestCase,
    FunctionUpstreamIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity.helpers import (
    build_table_function_graph_identities,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionReturnContractIdentityTestCase(
            description="table function return type changes identity",
            original_type="INTEGER",
            changed_type="BIGINT",
            expected_changed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_return_contract_change_when_hashing_then_identity_changes(
    test_case: FunctionReturnContractIdentityTestCase,
) -> None:
    function: CompiledFunction = replace(
        build_compiled_function(body_sql="SELECT 1 AS order_id"),
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.TABLE_FN,
            name="customer_orders",
        ),
        name="customer_orders",
        returns="TABLE",
        return_columns=(FunctionReturnColumn(name="order_id", type=test_case.original_type),),
    )
    changed_function: CompiledFunction = replace(
        function,
        return_columns=(FunctionReturnColumn(name="order_id", type=test_case.changed_type),),
    )

    original_hash: str = build_function_local_hashes(functions=(function,))[function.name]
    changed_hash: str = build_function_local_hashes(functions=(changed_function,))[
        changed_function.name
    ]

    assert (original_hash != changed_hash) is test_case.expected_changed


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionUpstreamIdentityTestCase(
            description="function upstream change reaches consumer identity",
            original_query="SELECT 1 AS order_id",
            changed_query="SELECT 2 AS order_id",
            expected_changed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_upstream_change_when_hashing_then_consumer_identity_changes(
    test_case: FunctionUpstreamIdentityTestCase,
) -> None:
    original: DirectModelVersionIdentities = build_table_function_graph_identities(
        base_query=test_case.original_query
    )
    changed: DirectModelVersionIdentities = build_table_function_graph_identities(
        base_query=test_case.changed_query
    )

    changed_identity: bool = (
        original.model_version_hashes["customer_order_summary"]
        != changed.model_version_hashes["customer_order_summary"]
    )
    assert changed_identity is test_case.expected_changed
