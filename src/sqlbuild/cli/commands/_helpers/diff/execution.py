"""Diff command execution phases."""

from __future__ import annotations

import sys
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
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    DiffCommandRequest,
    DiffInvocation,
    DirectDiffPreparation,
    QueryDiffPreparation,
    VirtualDiffPreparation,
    VirtualDiffRunOutcome,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
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
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.virtual.diff.main.diff import run_virtual_diff
from sqlbuild.virtual.diff.models import VirtualDiffOptions


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
) -> DiffExecutionResult:
    """Materialize, compare, and clean one raw-query pair."""

    adapter: BaseAdapter = preparation.adapter
    print("Query diff connection  START", file=sys.stderr)
    try:
        connection: Any = adapter.connect(preparation.connection_config)
    except Exception:
        print("Query diff connection  ERROR", file=sys.stderr)
        raise
    print("Query diff connection  OK", file=sys.stderr)
    left: QueryDiffArtifact = QueryDiffArtifactLifecycle.build(
        adapter=adapter,
        run_id=preparation.run_id,
        side="left",
        database=preparation.database,
        schema=preparation.schema,
    )
    right: QueryDiffArtifact = QueryDiffArtifactLifecycle.build(
        adapter=adapter,
        run_id=preparation.run_id,
        side="right",
        database=preparation.database,
        schema=preparation.schema,
    )
    created: list[QueryDiffArtifact] = []
    cleanup_errors: list[Exception] = []
    try:
        print("Query diff cleanup  START", file=sys.stderr)
        try:
            cleanup_result: QueryDiffArtifactCleanupResult = (
                QueryDiffArtifactLifecycle.cleanup_expired(
                    adapter=adapter,
                    connection=connection,
                    database=preparation.database,
                    schema=preparation.schema,
                    now=datetime.now(UTC),
                )
            )
        except Exception as error:
            print(
                "Query diff cleanup  WARNING  recovery cleanup could not inspect historical "
                f"ownership evidence: {error}",
                file=sys.stderr,
            )
        else:
            print(
                f"Query diff cleanup  OK  ({len(cleanup_result.cleaned)} expired)",
                file=sys.stderr,
            )
            for relation in cleanup_result.untracked:
                print(
                    "Query diff cleanup  WARNING  reserved-name relation lacks matching "
                    f"ownership evidence: {relation.name}",
                    file=sys.stderr,
                )
        artifact_lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple(
                (artifact.database, artifact.schema, artifact.name) for artifact in (left, right)
            ),
        )
        for artifact in (left, right):
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
        expires_at: datetime = ttl.add_to(datetime.now(UTC))
        _preflight_query_columns(
            adapter=adapter,
            connection=connection,
            sql=preparation.left_sql,
            label="left",
            max_columns=request.max_columns,
        )
        _preflight_query_columns(
            adapter=adapter,
            connection=connection,
            sql=preparation.right_sql,
            label="right",
            max_columns=request.max_columns,
        )
        print("Query diff materialization  START", file=sys.stderr)
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
            print("Query diff materialization  ERROR", file=sys.stderr)
            raise
        print(
            f"Query diff materialization  OK  ({preparation.schema}; expires "
            f"{expires_at.isoformat()})",
            file=sys.stderr,
        )
        print("Query diff comparison  START", file=sys.stderr)
        try:
            model_result: ModelDiffResult = execute_prepared_query_diff(
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
                ),
            )
        except Exception:
            print("Query diff comparison  ERROR", file=sys.stderr)
            raise
        print("Query diff comparison  OK", file=sys.stderr)
        return DiffExecutionResult(model_results=(model_result,))
    finally:
        active_error: BaseException | None = sys.exc_info()[1]
        print("Query diff immediate cleanup  START", file=sys.stderr)
        for artifact in reversed(created):
            try:
                QueryDiffArtifactLifecycle.cleanup(
                    adapter=adapter,
                    connection=connection,
                    artifact=artifact,
                )
            except Exception as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            print(
                f"Query diff immediate cleanup  ERROR  ({len(cleanup_errors)} failed)",
                file=sys.stderr,
            )
        else:
            print(
                f"Query diff immediate cleanup  OK  ({len(created)} removed)",
                file=sys.stderr,
            )
        adapter.close(connection)
        if cleanup_errors and active_error is None:
            raise cleanup_errors[0]


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
    columns: tuple[str, ...] = adapter.query_column_names(connection=connection, sql=sql)
    if not columns:
        raise CliUserError(f"{label} query returned no columns", code="C237")
    normalized: tuple[str, ...] = tuple(column.lower() for column in columns)
    duplicates: tuple[str, ...] = tuple(
        sorted({column for column in normalized if normalized.count(column) > 1})
    )
    if duplicates:
        raise CliUserError(
            f"{label} query returns duplicate column names: {', '.join(duplicates)}",
            code="C238",
            help="add unique aliases before comparing query results",
        )
    if max_columns is not None and len(columns) > max_columns:
        raise CliUserError(
            f"{label} query has {len(columns)} columns, exceeding --max-columns {max_columns}",
            code="C239",
        )


def prepare_virtual_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation
) -> VirtualDiffPreparation:
    """Resolve virtual diff adapter, connection, and sample limits."""

    if request.from_name is None or request.to_name is None:
        raise CliUserError("virtual diff requires FROM:TO", code="C236")
    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=invocation.discovered_inputs.project_config,
        local_config=invocation.discovered_inputs.local_config,
    )
    return VirtualDiffPreparation(
        from_virtual_environment=request.from_name,
        to_virtual_environment=request.to_name,
        adapter=resolve_adapter(
            adapter_name=effective_adapter_name,
            project_dir=invocation.effective_project_dir,
        ),
        connection_config=resolve_project_connection_config(
            discovered_inputs=invocation.discovered_inputs,
            project_dir=invocation.effective_project_dir,
            cli_vars=request.cli_vars,
        ),
        effective_max_column_examples=_effective_max_examples(
            explicit_value=request.max_column_examples, verbose=request.verbose
        ),
        effective_max_row_only_examples=_effective_max_examples(
            explicit_value=request.max_row_only_examples, verbose=request.verbose
        ),
        use_color=not request.no_color and supports_color(),
    )


def execute_virtual_diff(
    *, request: DiffCommandRequest, invocation: DiffInvocation, preparation: VirtualDiffPreparation
) -> VirtualDiffRunOutcome:
    """Execute a virtual environment diff."""

    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=sys.stdout,
        use_color=preparation.use_color,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=invocation.discovered_inputs.project_config,
            local_config=invocation.discovered_inputs.local_config,
        ),
        stream=sys.stdout,
        use_color=preparation.use_color,
    )
    (
        result,
        selected_names,
        skipped_names,
        from_stale,
        to_stale,
        from_working,
        to_working,
    ) = run_virtual_diff(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
        adapter=preparation.adapter,
        connection_config=preparation.connection_config,
        from_virtual_environment_name=preparation.from_virtual_environment,
        to_virtual_environment_name=preparation.to_virtual_environment,
        options=VirtualDiffOptions(
            no_sql_validation=request.no_sql_validation,
            select=request.select,
            exclude=request.exclude,
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
            tolerance_overrides=parse_cli_tolerance_overrides(values=request.tolerance_overrides),
            allow_partial_diff=request.allow_partial_diff,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        ),
        hooks=ConnectionHooks(
            on_progress=planning_progress.on_progress,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    return VirtualDiffRunOutcome(
        result=result,
        selected_names=selected_names,
        skipped_names=skipped_names,
        from_stale=from_stale,
        to_stale=to_stale,
        from_working=from_working,
        to_working=to_working,
    )


def _effective_max_examples(*, explicit_value: int | None, verbose: bool) -> int:
    return explicit_value if explicit_value is not None else (10 if verbose else 3)


def _sampling_override(*, request: DiffCommandRequest) -> RowDiffSamplingOverride:
    return RowDiffSamplingOverride(
        row_limit=request.sample_rows,
        seed=request.sample_seed,
        exhaustive=request.exhaustive,
    )
