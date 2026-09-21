"""Coarse native SQL-test planning and artifact rendering boundary."""

from __future__ import annotations

import time
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import NativeSqlTestPlanningError, PlannerInputError
from sqlbuild.compiler.planner.main.execution.sql_test_dialect import (
    restore_sql_test_dialect_function_names,
)
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact
from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.executor.testing.types import NativeSqlTestRenderingModule

_CALL_SUFFIX_SENTINEL: str = "__SQLBUILD_CALL_SUFFIX__"


def plan_and_render_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Plan and render SQL tests in one deterministic native project call."""

    if not tests:
        return ()
    start_ns: int = time.perf_counter_ns()
    functions: list[dict[str, object]] = []
    for function in project.functions:
        target: str | None = function.destination.qualified_name
        if target is None:
            continue
        udf_prefix, udf_suffix = _render_call_template(
            adapter.render_udf_call(
                target=target,
                call_suffix_sql=_CALL_SUFFIX_SENTINEL,
            )
        )
        table_function_prefix, table_function_suffix = _render_call_template(
            adapter.render_table_function_call(
                target=target,
                call_suffix_sql=_CALL_SUFFIX_SENTINEL,
            )
        )
        functions.append(
            {
                "name": function.name,
                "udfPrefix": udf_prefix,
                "udfSuffix": udf_suffix,
                "tableFunctionPrefix": table_function_prefix,
                "tableFunctionSuffix": table_function_suffix,
            }
        )
    request: dict[str, object] = {
        "models": _model_requests(project=project),
        "functions": functions,
        "tests": [_test_request(test) for test in tests],
        "sqlAnalysisEnabled": sql_analysis_enabled,
        "sqlAnalysisDialect": adapter.sql_analysis_dialect(),
        "setDifferenceOperator": adapter.render_set_difference_operator(),
        "requiresDerivedTableAliases": adapter.requires_derived_table_aliases(),
        "workers": 4,
    }
    try:
        native_response: str = cast(
            NativeSqlTestRenderingModule, _native
        ).plan_and_render_sql_tests_json(
            orjson.dumps(request, option=orjson.OPT_SORT_KEYS).decode()
        )
    except ValueError as error:
        message: str = str(error)
        if message.startswith("compile_input:"):
            raise CompileInputError(message.removeprefix("compile_input:")) from None
        if message.startswith("planner_input:"):
            raise PlannerInputError(message.removeprefix("planner_input:")) from None
        raise NativeSqlTestPlanningError(f"native SQL-test planning failed: {message}") from error
    response_payload: object = orjson.loads(native_response)
    if not isinstance(response_payload, dict):
        raise NativeSqlTestPlanningError(
            "native SQL-test planning returned an invalid batch response"
        )
    response: object = response_payload.get("artifacts")
    planning_ns: object = response_payload.get("planningNs")
    rendering_ns: object = response_payload.get("renderingNs")
    if (
        not isinstance(response, list)
        or len(response) != len(tests)
        or not isinstance(planning_ns, int)
        or isinstance(planning_ns, bool)
        or not isinstance(rendering_ns, int)
        or isinstance(rendering_ns, bool)
    ):
        raise NativeSqlTestPlanningError(
            "native SQL-test planning returned an invalid batch response"
        )
    artifacts: list[NativeSqlTestArtifact] = []
    for value in response:
        payload: dict[str, Any] | None = (
            cast(dict[str, Any], value) if isinstance(value, dict) else None
        )
        sql: object = payload.get("sql") if payload is not None else None
        model_names: object = payload.get("modelNames") if payload is not None else None
        warnings: object = payload.get("warnings") if payload is not None else None
        if (
            not isinstance(sql, str)
            or not isinstance(model_names, list)
            or not all(isinstance(name, str) for name in model_names)
            or not isinstance(warnings, list)
            or not all(isinstance(warning, dict) for warning in warnings)
        ):
            raise NativeSqlTestPlanningError("native SQL-test planning returned an invalid result")
        artifacts.append(
            NativeSqlTestArtifact(
                sql=restore_sql_test_dialect_function_names(
                    sql=sql,
                    dialect=adapter.sql_analysis_dialect(),
                ),
                model_names=tuple(cast(list[str], model_names)),
                warnings=tuple(cast(list[dict[str, object]], warnings)),
            )
        )
    elapsed_ns: int = time.perf_counter_ns() - start_ns
    boundary_overhead_ns: int = max(0, elapsed_ns - planning_ns - rendering_ns)
    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is not None:
        collector.add(
            phase="test_planning_ms",
            elapsed_ns=planning_ns + boundary_overhead_ns,
        )
        collector.add(phase="comparison_render_ms", elapsed_ns=rendering_ns)
    return tuple(artifacts)


def _test_request(test: CompiledSqlTest) -> dict[str, object]:
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
    if isinstance(payload, CompiledDirectLogicSqlTestPayload):
        payload_request: dict[str, object] = {
            "kind": "direct",
            "mode": payload.mode.value,
            "actualCte": _cte_request(payload.actual_cte),
            "expectedCte": _cte_request(payload.expected_cte),
            "helperCtes": [_cte_request(cte) for cte in payload.helper_ctes],
        }
    else:
        payload_request = {
            "kind": "model",
            "authoredCtes": [_cte_request(cte) for cte in payload.authored_ctes],
            "modelQueryOverrides": payload.model_query_overrides,
            "expectedCtes": [_cte_request(cte) for cte in payload.expected_ctes],
            "expectedModelNames": list(payload.expected_model_names),
            "assertionCtes": [_cte_request(cte) for cte in payload.assertion_ctes],
        }
    return {
        "name": test.name,
        "fileLabel": str(test.test_file.relative_path),
        "payload": payload_request,
    }


def _model_requests(*, project: CompiledProject) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    for model in project.models:
        dependencies: list[str] = []
        for dependency in model.deps:
            if dependency.resource_type == CompiledResourceType.MODEL:
                dependencies.append(dependency.name)
        requests.append(
            {
                "name": model.name,
                "querySql": model.query_sql,
                "modelDependencies": dependencies,
            }
        )
    return requests


def _cte_request(cte: CompileSqlTestCte) -> dict[str, str]:
    return {"name": cte.name, "sqlBody": cte.sql_body}


def _render_call_template(rendered: str) -> tuple[str, str]:
    prefix, separator, suffix = rendered.partition(_CALL_SUFFIX_SENTINEL)
    if not separator or _CALL_SUFFIX_SENTINEL in suffix:
        raise NativeSqlTestPlanningError("adapter SQL function call template is not deterministic")
    return prefix, suffix
