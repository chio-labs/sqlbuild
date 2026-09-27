"""Diff command execution phases."""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.cli.commands._helpers.runtime.connection import (
    resolve_project_connection_config,
    resolve_target_connection_config,
)
from sqlbuild.cli.commands.constants import READ_ONLY_QUERY_ROOT_KEYS
from sqlbuild.cli.commands.exceptions import CliUserError, QueryDiffExecutionError
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    DirectDiffPreparation,
    QueryDiffPreparation,
    QueryDiffRunOutcome,
)
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.effective_target_namespace import (
    build_effective_target_namespace,
)
from sqlbuild.compiler.pipeline.main.diff import run_diff_pipeline
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.executor.diff.classes.query_artifact_lifecycle import QueryDiffArtifactLifecycle
from sqlbuild.executor.diff.main.config import parse_cli_tolerance_overrides
from sqlbuild.executor.diff.main.execute import execute_diff
from sqlbuild.executor.diff.main.execute_query import (
    execute_query_diff as execute_prepared_query_diff,
)
from sqlbuild.executor.diff.models import (
    DiffExecutionOptions,
    DiffExecutionResult,
    ModelDiffResult,
    QueryDiffArtifact,
    QueryDiffArtifactCleanupResult,
    RowDiffSamplingOverride,
)
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def prepare_direct_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation
) -> DirectDiffPreparation:
    """Resolve direct target diff adapter, compiled projects, and limits."""

    if request.from_name is None or request.to_name is None:
        raise CliUserError("model diff requires FROM:TO", code="C224")
    from_target: str = request.from_name
    to_target: str = request.to_name
    if from_target not in invocation.discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff FROM target '{from_target}'", code="C205")
    if to_target not in invocation.discovered_inputs.project_config.targets:
        raise CliUserError(f"unknown diff TO target '{to_target}'", code="C206")
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=effective_adapter_name, project_dir=invocation.effective_project_dir
    )
    connection_config: dict[str, object] = resolve_target_connection_config(
        discovered_inputs=invocation.discovered_inputs,
        project_dir=invocation.effective_project_dir,
        target_name=to_target,
        cli_vars=request.cli_vars,
    )
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    left_project, right_project, selected_names = run_diff_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=adapter,
        from_target=from_target,
        to_target=to_target,
        resolved_connection=connection_config,
        no_sql_validation=request.no_sql_validation,
        select=request.select,
        exclude=request.exclude,
        cli_vars=request.cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )
    if not selected_names:
        raise CliUserError("no diffable models found in the selected scope", code="C207")
    return DirectDiffPreparation(
        from_target=from_target,
        to_target=to_target,
        adapter=adapter,
        left_project=left_project,
        right_project=right_project,
        selected_names=selected_names,
        connection_config=connection_config,
        effective_max_column_examples=_effective_max_examples(
            explicit_value=request.max_column_examples, verbose=request.verbose
        ),
        effective_max_row_only_examples=_effective_max_examples(
            explicit_value=request.max_row_only_examples, verbose=request.verbose
        ),
    )


def execute_direct_diff(
    *, request: DiffCommandRequest, preparation: DirectDiffPreparation
) -> DiffExecutionResult:
    """Execute a direct target-to-target diff."""

    connection: Any = preparation.adapter.connect(preparation.connection_config)
    try:
        return execute_diff(
            adapter=preparation.adapter,
            connection=connection,
            left_project=preparation.left_project,
            right_project=preparation.right_project,
            selected_names=preparation.selected_names,
            options=DiffExecutionOptions(
                schema_only=request.schema_only,
                bounded=request.bounded,
                collect_samples=not request.schema_only,
                max_column_examples=preparation.effective_max_column_examples,
                max_row_only_examples=preparation.effective_max_row_only_examples,
                max_models=request.max_models,
                max_columns=request.max_columns,
                sampling_override=_sampling_override(request=request),
                unique_key_override=request.unique_key_override,
                unkeyed=request.unkeyed,
                excluded_columns_override=request.excluded_columns_override,
                tolerance_overrides=parse_cli_tolerance_overrides(
                    values=request.tolerance_overrides
                ),
            ),
        )
    finally:
        preparation.adapter.close(connection)


def prepare_query_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation
) -> QueryDiffPreparation:
    """Resolve raw SQL, active target namespace, adapter, and connection."""

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=effective_adapter_name,
        project_dir=invocation.effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=invocation.discovered_inputs,
        project_dir=invocation.effective_project_dir,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    connection_database: object | None = connection_config.get("database")
    if effective_adapter_name in {
        BuiltinAdapter.DUCKDB.value,
        BuiltinAdapter.MOTHERDUCK.value,
    }:
        connection_database = None
    target_name, _target, database, schema = build_effective_target_namespace(
        discovered_inputs=invocation.discovered_inputs,
        selected_target=request.selected_target,
        connection_database=connection_database,
        connection_schema=connection_config.get("schema"),
        default_database=adapter.default_database(),
        default_schema=adapter.default_schema(),
    )
    if schema is None:
        raise CliUserError(
            "raw-query diff requires an active target schema",
            code="C227",
            help="configure the selected target schema before running the comparison",
        )
    left_sql: str = _resolve_query_input(
        inline=request.left_query,
        file=request.left_query_file,
        label="left",
    )
    right_sql: str = _resolve_query_input(
        inline=request.right_query,
        file=request.right_query_file,
        label="right",
    )
    left_sql = _validate_read_only_query(sql=left_sql, label="left", adapter=adapter)
    right_sql = _validate_read_only_query(sql=right_sql, label="right", adapter=adapter)
    _runtime_target, _effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=invocation.discovered_inputs,
        selected_target=request.selected_target,
        cli_vars=request.cli_vars,
    )
    return QueryDiffPreparation(
        adapter=adapter,
        connection_config=connection_config,
        left_sql=left_sql,
        right_sql=right_sql,
        left_label=(request.left_label or "left query").strip(),
        right_label=(request.right_label or "right query").strip(),
        selected_target=target_name,
        database=database,
        schema=schema,
        run_id=run_id,
        artifact_ttl=invocation.discovered_inputs.project_config.diff.query_artifact_ttl,
        effective_max_column_examples=_effective_max_examples(
            explicit_value=request.max_column_examples,
            verbose=request.verbose,
        ),
        effective_max_row_only_examples=_effective_max_examples(
            explicit_value=request.max_row_only_examples,
            verbose=request.verbose,
        ),
    )


def execute_query_diff(
    *, request: DiffCommandRequest, preparation: QueryDiffPreparation
) -> QueryDiffRunOutcome:
    """Materialize, compare, and clean one raw-query pair."""

    adapter: BaseAdapter = preparation.adapter
    total_started_at: float = time.perf_counter()
    phase_seconds: dict[str, float] = {}
    print("Query diff connection  START", file=sys.stderr)
    connection_started_at: float = time.perf_counter()
    try:
        connection: Any = adapter.connect(preparation.connection_config)
    except Exception:
        connection_elapsed: float = time.perf_counter() - connection_started_at
        print(f"Query diff connection  ERROR  ({connection_elapsed:.2f}s)", file=sys.stderr)
        print(
            f"Query diff total  ERROR  ({time.perf_counter() - total_started_at:.2f}s)",
            file=sys.stderr,
        )
        raise
    phase_seconds["connection"] = time.perf_counter() - connection_started_at
    print(f"Query diff connection  OK  ({phase_seconds['connection']:.2f}s)", file=sys.stderr)
    left, right = _build_query_diff_artifacts(adapter=adapter, preparation=preparation)
    created: list[QueryDiffArtifact] = []
    cleanup_errors: list[Exception] = []
    model_result: ModelDiffResult | None = None
    try:
        phase_seconds["reconciliation"] = _reconcile_query_diff_artifacts(
            adapter=adapter,
            connection=connection,
            preparation=preparation,
        )
        expires_at, phase_seconds["inspection"] = _inspect_query_diff_inputs(
            adapter=adapter,
            connection=connection,
            preparation=preparation,
            artifacts=(left, right),
            max_columns=request.max_columns,
        )
        print("Query diff materialization  START", file=sys.stderr)
        materialization_started_at: float = time.perf_counter()
        try:
            QueryDiffArtifactLifecycle.materialize(
                adapter=adapter,
                connection=connection,
                artifact=left,
                sql=preparation.left_sql,
                expires_at=expires_at,
            )
            created.append(left)
            QueryDiffArtifactLifecycle.materialize(
                adapter=adapter,
                connection=connection,
                artifact=right,
                sql=preparation.right_sql,
                expires_at=expires_at,
            )
            created.append(right)
        except Exception:
            phase_seconds["materialization"] = time.perf_counter() - materialization_started_at
            print(
                f"Query diff materialization  ERROR  ({phase_seconds['materialization']:.2f}s)",
                file=sys.stderr,
            )
            raise
        phase_seconds["materialization"] = time.perf_counter() - materialization_started_at
        print(
            f"Query diff materialization  OK  ({preparation.schema}; expires "
            f"{expires_at.isoformat()}; {phase_seconds['materialization']:.2f}s)",
            file=sys.stderr,
        )
        print("Query diff comparison  START", file=sys.stderr)
        comparison_started_at: float = time.perf_counter()
        try:
            model_result = execute_prepared_query_diff(
                adapter=adapter,
                connection=connection,
                left_relation=left.relation,
                right_relation=right.relation,
                options=DiffExecutionOptions(
                    schema_only=request.schema_only,
                    collect_samples=not request.schema_only,
                    max_column_examples=preparation.effective_max_column_examples,
                    max_row_only_examples=preparation.effective_max_row_only_examples,
                    max_columns=request.max_columns,
                    sampling_override=_sampling_override(request=request),
                    unique_key_override=request.unique_key_override,
                    unkeyed=request.unkeyed,
                    excluded_columns_override=request.excluded_columns_override,
                    tolerance_overrides=parse_cli_tolerance_overrides(
                        values=request.tolerance_overrides
                    ),
                    comparison_name=(f"{preparation.left_label} vs {preparation.right_label}"),
                ),
            )
        except Exception:
            phase_seconds["comparison"] = time.perf_counter() - comparison_started_at
            print(
                f"Query diff comparison  ERROR  ({phase_seconds['comparison']:.2f}s)",
                file=sys.stderr,
            )
            raise
        phase_seconds["comparison"] = time.perf_counter() - comparison_started_at
        print(f"Query diff comparison  OK  ({phase_seconds['comparison']:.2f}s)", file=sys.stderr)
    finally:
        active_error: BaseException | None = sys.exc_info()[1]
        cleanup_errors, phase_seconds["cleanup"] = _cleanup_query_diff_artifacts(
            adapter=adapter,
            connection=connection,
            created=created,
        )
        phase_seconds["total"] = time.perf_counter() - total_started_at
        total_status: str = "ERROR" if active_error is not None or cleanup_errors else "OK"
        print(
            f"Query diff total  {total_status}  ({phase_seconds['total']:.2f}s)",
            file=sys.stderr,
        )
        if cleanup_errors:
            raise cleanup_errors[0]
    if model_result is None:
        raise QueryDiffExecutionError(
            "query diff comparison completed without a result", code="C256"
        )
    result: DiffExecutionResult = DiffExecutionResult(model_results=(model_result,))
    outcome, exit_code = _resolve_query_diff_outcome(request=request, result=result)
    return QueryDiffRunOutcome(
        result=result,
        phase_seconds=phase_seconds,
        outcome=outcome,
        exit_code=exit_code,
    )


def _build_query_diff_artifacts(
    *, adapter: BaseAdapter, preparation: QueryDiffPreparation
) -> tuple[QueryDiffArtifact, QueryDiffArtifact]:
    return (
        QueryDiffArtifactLifecycle.build(
            adapter=adapter,
            run_id=preparation.run_id,
            side="left",
            database=preparation.database,
            schema=preparation.schema,
        ),
        QueryDiffArtifactLifecycle.build(
            adapter=adapter,
            run_id=preparation.run_id,
            side="right",
            database=preparation.database,
            schema=preparation.schema,
        ),
    )


def _cleanup_query_diff_artifacts(
    *,
    adapter: BaseAdapter,
    connection: Any,
    created: list[QueryDiffArtifact],
) -> tuple[list[Exception], float]:
    print("Query diff immediate cleanup  START", file=sys.stderr)
    started_at: float = time.perf_counter()
    errors: list[Exception] = []
    for artifact in reversed(created):
        try:
            QueryDiffArtifactLifecycle.cleanup(
                adapter=adapter,
                connection=connection,
                artifact=artifact,
            )
        except Exception as error:
            errors.append(error)
    try:
        adapter.close(connection)
    except Exception as error:
        errors.append(error)
    elapsed: float = time.perf_counter() - started_at
    if errors:
        print(
            f"Query diff immediate cleanup  ERROR  ({len(errors)} failed; {elapsed:.2f}s)",
            file=sys.stderr,
        )
    else:
        print(
            f"Query diff immediate cleanup  OK  ({len(created)} removed; {elapsed:.2f}s)",
            file=sys.stderr,
        )
    return errors, elapsed


def _resolve_query_diff_outcome(
    *, request: DiffCommandRequest, result: DiffExecutionResult
) -> tuple[str, int]:
    if not request.schema_only and _query_schema_prevented_row_comparison(result=result):
        return "incomplete", 2
    if _query_result_has_findings(result=result):
        return "findings", 1
    return "pass", 0


def _query_schema_prevented_row_comparison(*, result: DiffExecutionResult) -> bool:
    return any(
        model.row_result is None
        and (
            model.schema_result.added_columns
            or model.schema_result.removed_columns
            or model.schema_result.type_changed_columns
        )
        for model in result.model_results
    )


def _query_result_has_findings(*, result: DiffExecutionResult) -> bool:
    return any(
        model.schema_result.added_columns
        or model.schema_result.removed_columns
        or model.schema_result.type_changed_columns
        or (
            model.row_result is not None
            and (
                model.row_result.unequal_count
                or model.row_result.left_only_count
                or model.row_result.right_only_count
            )
        )
        for model in result.model_results
    )


def _inspect_query_diff_inputs(
    *,
    adapter: BaseAdapter,
    connection: Any,
    preparation: QueryDiffPreparation,
    artifacts: tuple[QueryDiffArtifact, QueryDiffArtifact],
    max_columns: int | None,
) -> tuple[datetime, float]:
    print("Query diff inspection  START", file=sys.stderr)
    started_at: float = time.perf_counter()
    try:
        artifact_lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple(
                (artifact.database, artifact.schema, artifact.name) for artifact in artifacts
            ),
        )
        for artifact in artifacts:
            if artifact_lookup.exists(
                database=artifact.database,
                schema=artifact.schema,
                name=artifact.name,
            ):
                raise CliUserError(
                    f"query-diff artifact already exists: {artifact.relation}",
                    code="C245",
                    help="wait for its TTL cleanup or investigate the reserved-name relation",
                )
        ttl: Duration | None = Duration.parse(preparation.artifact_ttl)
        if ttl is None:
            raise CliUserError("diff.query_artifact_ttl must be a positive duration", code="C228")
        _preflight_query_columns(
            adapter=adapter,
            connection=connection,
            sql=preparation.left_sql,
            label=preparation.left_label,
            max_columns=max_columns,
        )
        _preflight_query_columns(
            adapter=adapter,
            connection=connection,
            sql=preparation.right_sql,
            label=preparation.right_label,
            max_columns=max_columns,
        )
    except Exception:
        elapsed: float = time.perf_counter() - started_at
        print(
            f"Query diff inspection  ERROR  ({elapsed:.2f}s)",
            file=sys.stderr,
        )
        raise
    elapsed = time.perf_counter() - started_at
    print(f"Query diff inspection  OK  ({elapsed:.2f}s)", file=sys.stderr)
    return ttl.add_to(datetime.now(UTC)), elapsed


def _reconcile_query_diff_artifacts(
    *,
    adapter: BaseAdapter,
    connection: Any,
    preparation: QueryDiffPreparation,
) -> float:
    print("Query diff reconciliation  START", file=sys.stderr)
    started_at: float = time.perf_counter()
    try:
        result: QueryDiffArtifactCleanupResult = QueryDiffArtifactLifecycle.cleanup_expired(
            adapter=adapter,
            connection=connection,
            database=preparation.database,
            schema=preparation.schema,
            now=datetime.now(UTC),
        )
    except Exception as error:
        elapsed: float = time.perf_counter() - started_at
        print(
            "Query diff reconciliation  WARNING  recovery cleanup could not inspect historical "
            f"ownership evidence: {error} ({elapsed:.2f}s)",
            file=sys.stderr,
        )
        return elapsed
    elapsed = time.perf_counter() - started_at
    print(
        f"Query diff reconciliation  OK  ({len(result.cleaned)} expired; {elapsed:.2f}s)",
        file=sys.stderr,
    )
    for relation in result.untracked:
        print(
            "Query diff reconciliation  WARNING  reserved-name relation lacks matching "
            f"ownership evidence: {relation.name}",
            file=sys.stderr,
        )
    return elapsed


def _resolve_query_input(*, inline: str | None, file: Path | None, label: str) -> str:
    if inline is not None:
        return inline
    if file is None:
        raise CliUserError(f"raw-query diff requires a {label} query", code="C229")
    if not file.exists() or not file.is_file():
        raise CliUserError(f"{label} query file does not exist: {file}", code="C230")
    try:
        return file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CliUserError(
            f"{label} query file could not be read as UTF-8: {file}", code="C231"
        ) from error


def _validate_read_only_query(*, sql: str, label: str, adapter: BaseAdapter) -> str:
    normalized_sql: str = sql.strip()
    if normalized_sql.endswith(";"):
        normalized_sql = normalized_sql[:-1].rstrip()
    if not normalized_sql:
        raise CliUserError(f"{label} query must not be empty", code="C232")
    polyglot: Any | None = import_polyglot_sql()
    if polyglot is None:
        raise CliUserError("raw-query diff requires the bundled SQL parser", code="C233")
    try:
        expression: Any = polyglot.parse_one(
            normalized_sql,
            dialect=adapter.sql_analysis_dialect() or "generic",
        )
    except Exception as error:
        raise CliUserError(
            f"{label} query is not one valid SQL statement: {error}", code="C234"
        ) from error
    if str(getattr(expression, "key", "")).lower() not in READ_ONLY_QUERY_ROOT_KEYS:
        raise CliUserError(
            f"{label} query must be one read-only SELECT, WITH, or VALUES expression",
            code="C235",
        )
    mutating_keys: frozenset[str] = frozenset(
        {
            "alter",
            "command",
            "copy",
            "create",
            "delete",
            "drop",
            "execute",
            "grant",
            "insert",
            "load_data",
            "merge",
            "pragma",
            "revoke",
            "set",
            "transaction",
            "truncate",
            "uncache",
            "update",
            "use",
        }
    )
    if any(str(getattr(node, "key", "")).lower() in mutating_keys for node in expression.walk()):
        raise CliUserError(
            f"{label} query must not contain data-changing or administrative statements",
            code="C240",
        )
    expression_args: object = getattr(expression, "args", {})
    if isinstance(expression_args, dict) and (
        expression_args.get("into") is not None or bool(expression_args.get("locks"))
    ):
        raise CliUserError(
            f"{label} query must not write a relation or acquire row locks",
            code="C244",
        )
    return normalized_sql


def _preflight_query_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    sql: str,
    label: str,
    max_columns: int | None,
) -> None:
    display_label: str = label if label.lower().endswith("query") else f"{label} query"
    columns: tuple[str, ...] = adapter.query_column_names(connection=connection, sql=sql)
    if not columns:
        raise CliUserError(f"{display_label} returned no columns", code="C237")
    normalized: tuple[str, ...] = tuple(column.lower() for column in columns)
    duplicates: tuple[str, ...] = tuple(
        sorted({column for column in normalized if normalized.count(column) > 1})
    )
    if duplicates:
        raise CliUserError(
            f"{display_label} returns duplicate column names: {', '.join(duplicates)}",
            code="C238",
            help="add unique aliases before comparing query results",
        )
    if max_columns is not None and len(columns) > max_columns:
        raise CliUserError(
            f"{display_label} has {len(columns)} columns, exceeding --max-columns {max_columns}",
            code="C239",
        )


def _effective_max_examples(*, explicit_value: int | None, verbose: bool) -> int:
    return explicit_value if explicit_value is not None else (10 if verbose else 3)


def _sampling_override(*, request: DiffCommandRequest) -> RowDiffSamplingOverride:
    return RowDiffSamplingOverride(
        row_limit=request.sample_rows,
        seed=request.sample_seed,
        exhaustive=request.exhaustive,
    )
