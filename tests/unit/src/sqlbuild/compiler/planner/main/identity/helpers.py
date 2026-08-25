from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompileModelConfig,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.graph.core import build_downstream_deps
from sqlbuild.compiler.planner._helpers.identity.direct import (
    build_direct_model_version_identities,
)
from sqlbuild.compiler.planner.models import DirectModelVersionIdentities, PlannerScope
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import build_compiled_function


def build_table_function_graph_identities(*, base_query: str) -> DirectModelVersionIdentities:
    base_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.TABLE_FN,
        name="customer_orders",
    )
    consumer_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="customer_order_summary",
    )
    base_model: CompiledModel = _build_model(
        key=base_key,
        query_sql=base_query,
        deps=(),
    )
    consumer_model: CompiledModel = _build_model(
        key=consumer_key,
        query_sql='SELECT * FROM __table_fn("customer_orders")()',
        deps=(function_key,),
    )
    function: CompiledFunction = replace(
        build_compiled_function(body_sql='SELECT * FROM __ref("orders")'),
        key=function_key,
        deps=(base_key,),
        name=function_key.name,
        returns="TABLE",
        return_columns=(FunctionReturnColumn(name="order_id", type="INTEGER"),),
    )
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        base_key: (),
        function_key: (base_key,),
        consumer_key: (function_key,),
    }
    scope: PlannerScope = PlannerScope(
        upstream_deps=upstream,
        downstream_deps=build_downstream_deps(upstream),
        all_keys={key.name: key for key in upstream},
        models_by_name={
            base_model.name: base_model,
            consumer_model.name: consumer_model,
        },
        selected_keys=frozenset(upstream),
        execution_order=(base_key, function_key, consumer_key),
    )
    return build_direct_model_version_identities(functions=(function,), scope=scope)


def _build_model(
    *,
    key: CompiledObjectKey,
    query_sql: str,
    deps: tuple[CompiledObjectKey, ...],
) -> CompiledModel:
    return CompiledModel(
        key=key,
        deps=deps,
        name=key.name,
        relative_path=Path(f"models/{key.name}.sql"),
        query_sql=query_sql,
        config=CompileModelConfig(),
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=key.name,
            qualified_name=key.name,
        ),
    )
