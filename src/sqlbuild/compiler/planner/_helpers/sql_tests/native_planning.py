"""Native SQL-test chain planning and comparison rendering boundary."""

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
from sqlbuild.compiler.planner.models import (
    ChainStep,
    NativeSqlTestArtifact,
    NativeSqlTestPlan,
    PlanWarning,
    SqlTestAssertionStep,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.executor.testing.types import NativeSqlTestRenderingModule

_CALL_SUFFIX_SENTINEL: str = "__SQLBUILD_CALL_SUFFIX__"
_NATIVE_WORKERS: int = 4


def plan_and_render_sql_test_artifacts(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
) -> tuple[NativeSqlTestArtifact, ...]:
    """Plan and render SQL tests in one deterministic native project call."""

    artifacts: list[NativeSqlTestArtifact] = []
    for plan in plan_sql_tests_natively(
        project=project,
        tests=tests,
        adapter=adapter,
        sql_analysis_enabled=sql_analysis_enabled,
        render_sql=True,
    ):
        if plan.sql is None:
            raise NativeSqlTestPlanningError("native SQL-test planning omitted rendered SQL")
        artifacts.append(
            NativeSqlTestArtifact(
                sql=plan.sql,
                model_names=plan.model_names,
                error_messages=sql_test_plan_error_messages(warnings=plan.warnings),
            )
        )
    return tuple(artifacts)


def sql_test_plan_error_messages(*, warnings: tuple[PlanWarning, ...]) -> tuple[str, ...]:
    """Return each distinct ERROR-severity planning message for one SQL test, in order."""

    return tuple(
        dict.fromkeys(
            warning.message for warning in warnings if warning.severity is WarningSeverity.ERROR
        )
    )


def plan_sql_tests_natively(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    sql_analysis_enabled: bool,
    render_sql: bool,
) -> tuple[NativeSqlTestPlan, ...]:
    """Plan SQL-test chains and assertions in one native batch, optionally rendering SQL."""

    if not tests:
        return ()
    start_ns: int = time.perf_counter_ns()
    request: dict[str, object] = {
        "models": _model_requests(project=project),
        "functions": _function_requests(project=project, adapter=adapter),
        "tests": [_test_request(test=test) for test in tests],
        "sqlAnalysisEnabled": sql_analysis_enabled,
        "sqlAnalysisDialect": adapter.sql_analysis_dialect(),
        "setDifferenceOperator": adapter.render_set_difference_operator(),
        "requiresDerivedTableAliases": adapter.requires_derived_table_aliases(),
        "workers": _NATIVE_WORKERS,
        "renderSql": render_sql,
    }
    try:
        native_response: str = cast(
            NativeSqlTestRenderingModule, _native
        ).plan_and_render_sql_tests_json(
            orjson.dumps(request, option=orjson.OPT_SORT_KEYS).decode()
        )
    except ValueError as error:
        raise _planning_error(error=error) from None
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
    dialect: str | None = adapter.sql_analysis_dialect()
    plans: tuple[NativeSqlTestPlan, ...] = tuple(
        _plan_from_payload(value=value, dialect=dialect) for value in response
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
    return plans


def resolve_sql_test_model_chains(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> tuple[tuple[str, ...], ...]:
    """Return each test's ordered unmocked model chain; direct-logic tests have none."""

    if not tests:
        return ()
    request: dict[str, object] = {
        "models": _model_requests(project=project),
        "tests": [_test_request(test=test) for test in tests],
    }
    try:
        native_response: str = cast(
            NativeSqlTestRenderingModule, _native
        ).resolve_sql_test_chains_json(orjson.dumps(request, option=orjson.OPT_SORT_KEYS).decode())
    except ValueError as error:
        raise _planning_error(error=error) from None
    response_payload: object = orjson.loads(native_response)
    chains: object = response_payload.get("chains") if isinstance(response_payload, dict) else None
    if not isinstance(chains, list) or len(chains) != len(tests):
        raise NativeSqlTestPlanningError(
            "native SQL-test chain resolution returned an invalid response"
        )
    return tuple(_string_tuple(value=chain, context="chain") for chain in chains)


def _planning_error(*, error: ValueError) -> Exception:
    message: str = str(error)
    if message.startswith("compile_input:"):
        return CompileInputError(message.removeprefix("compile_input:"))
    if message.startswith("planner_input:"):
        return PlannerInputError(message.removeprefix("planner_input:"))
    return NativeSqlTestPlanningError(f"native SQL-test planning failed: {message}")


def _plan_from_payload(*, value: object, dialect: str | None) -> NativeSqlTestPlan:
    payload: dict[str, Any] = _object(value=value, context="result")
    sql: object = payload.get("sql")
    chain: object = payload.get("chain")
    assertions: object = payload.get("assertions")
    warnings: object = payload.get("warnings")
    if (
        (sql is not None and not isinstance(sql, str))
        or not isinstance(chain, list)
        or not isinstance(assertions, list)
        or not isinstance(warnings, list)
    ):
        raise NativeSqlTestPlanningError("native SQL-test planning returned an invalid result")
    return NativeSqlTestPlan(
        chain=tuple(_chain_step(value=step) for step in chain),
        assertions=tuple(_assertion_step(value=step) for step in assertions),
        model_names=_string_tuple(value=payload.get("modelNames"), context="model names"),
        warnings=tuple(_warning(value=warning) for warning in warnings),
        sql=(
            restore_sql_test_dialect_function_names(sql=sql, dialect=dialect)
            if isinstance(sql, str)
            else None
        ),
    )


def _chain_step(*, value: object) -> ChainStep:
    payload: dict[str, Any] = _object(value=value, context="chain step")
    return ChainStep(
        model_name=_string(value=payload.get("modelName"), context="chain step model"),
        resolved_sql=_string(value=payload.get("resolvedSql"), context="chain step SQL"),
        expected_cte_sql=_optional_string(
            value=payload.get("expectedCteSql"), context="chain step expected SQL"
        ),
        lifted_ctes=_cte_pairs(value=payload.get("liftedCtes")),
        comparison_body_sql=_optional_string(
            value=payload.get("comparisonBodySql"), context="chain step comparison SQL"
        ),
        expected_columns=_optional_string_tuple(
            value=payload.get("expectedColumns"), context="chain step expected columns"
        ),
    )


def _assertion_step(*, value: object) -> SqlTestAssertionStep:
    payload: dict[str, Any] = _object(value=value, context="assertion step")
    return SqlTestAssertionStep(
        name=_string(value=payload.get("name"), context="assertion name"),
        resolved_sql=_string(value=payload.get("resolvedSql"), context="assertion SQL"),
        lifted_ctes=_cte_pairs(value=payload.get("liftedCtes")),
        comparison_body_sql=_optional_string(
            value=payload.get("comparisonBodySql"), context="assertion comparison SQL"
        ),
    )


def _warning(*, value: object) -> PlanWarning:
    payload: dict[str, Any] = _object(value=value, context="warning")
    return PlanWarning(
        model_name=_optional_string(value=payload.get("modelName"), context="warning model"),
        severity=WarningSeverity(
            _string(value=payload.get("severity"), context="warning severity")
        ),
        message=_string(value=payload.get("message"), context="warning message"),
    )


def _cte_pairs(*, value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise NativeSqlTestPlanningError("native SQL-test planning returned invalid lifted CTEs")
    pairs: list[tuple[str, str]] = []
    for pair in value:
        name, sql = _string_tuple(value=pair, context="lifted CTE")
        pairs.append((name, sql))
    return tuple(pairs)


def _object(*, value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return cast(dict[str, Any], value)


def _string(*, value: object, context: str) -> str:
    if not isinstance(value, str):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return value


def _optional_string(*, value: object, context: str) -> str | None:
    return None if value is None else _string(value=value, context=context)


def _optional_string_tuple(*, value: object, context: str) -> tuple[str, ...] | None:
    return None if value is None else _string_tuple(value=value, context=context)


def _string_tuple(*, value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise NativeSqlTestPlanningError(f"native SQL-test planning returned an invalid {context}")
    return tuple(_string(value=item, context=context) for item in value)


def _function_requests(
    *, project: CompiledProject, adapter: BaseAdapter
) -> list[dict[str, object]]:
    functions: list[dict[str, object]] = []
    for function in project.functions:
        target: str | None = function.destination.qualified_name
        if target is None:
            continue
        udf_prefix, udf_suffix = _render_call_template(
            rendered=adapter.render_udf_call(
                target=target,
                call_suffix_sql=_CALL_SUFFIX_SENTINEL,
            )
        )
        table_function_prefix, table_function_suffix = _render_call_template(
            rendered=adapter.render_table_function_call(
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
    return functions


def _test_request(*, test: CompiledSqlTest) -> dict[str, object]:
    payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload = test.payload
    if isinstance(payload, CompiledDirectLogicSqlTestPayload):
        payload_request: dict[str, object] = {
            "kind": "direct",
            "mode": payload.mode.value,
            "actualCte": _cte_request(cte=payload.actual_cte),
            "expectedCte": _cte_request(cte=payload.expected_cte),
            "helperCtes": [_cte_request(cte=cte) for cte in payload.helper_ctes],
        }
    else:
        payload_request = {
            "kind": "model",
            "authoredCtes": [_cte_request(cte=cte) for cte in payload.authored_ctes],
            "modelQueryOverrides": payload.model_query_overrides,
            "expectedCtes": [_cte_request(cte=cte) for cte in payload.expected_ctes],
            "expectedModelNames": list(payload.expected_model_names),
            "assertionCtes": [_cte_request(cte=cte) for cte in payload.assertion_ctes],
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


def _cte_request(*, cte: CompileSqlTestCte) -> dict[str, str]:
    return {"name": cte.name, "sqlBody": cte.sql_body}


def _render_call_template(*, rendered: str) -> tuple[str, str]:
    prefix, separator, suffix = rendered.partition(_CALL_SUFFIX_SENTINEL)
    if not separator or _CALL_SUFFIX_SENTINEL in suffix:
        raise NativeSqlTestPlanningError("adapter SQL function call template is not deterministic")
    return prefix, suffix
