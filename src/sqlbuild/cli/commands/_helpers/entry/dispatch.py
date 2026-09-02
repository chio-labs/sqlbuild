"""CLI command dispatch from a parsed namespace to injected handlers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.diff.validation import parse_diff_name_range
from sqlbuild.cli.commands._helpers.entry.parsing import read_selector_file_inputs
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import (
    DBT_INIT_COMMAND,
    KATA_SKILLS_COMMAND,
    SCENARIO_CAPTURE_COMMAND,
    SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
    SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
    SCENARIO_CLI_MISSING_SUBCOMMAND,
    SCENARIO_TEST_COMMAND,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    AuditCommandRequest,
    BuildCommandRequest,
    CheckCommandRequest,
    CliEntrypointHandlers,
    CloneCommandRequest,
    CompileCommandRequest,
    CompileProfileFlags,
    CostCommandRequest,
    DbtInitCommandRequest,
    DiffCommandRequest,
    FreshnessCommandRequest,
    JanitorCommandRequest,
    KataCommandRequest,
    LoadCommandRequest,
    PlanCommandRequest,
    PlaygroundCommandRequest,
    PromoteCommandRequest,
    RollbackCommandRequest,
    ScenarioCaptureCommandRequest,
    ScenarioSnapshotLimitInputs,
    ScenarioTestCommandRequest,
    ScopeCommandRequest,
    SeedCommandRequest,
    SelectorInputs,
    TestCommandRequest,
)
from sqlbuild.cli.commands.types import CliCommand, CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def dispatch_cli_command(*, args: CliNamespace, handlers: CliEntrypointHandlers) -> int:
    """Route a parsed CLI namespace to its command handler and return its exit code."""

    project_dir: Path | None = None if args.project_dir is None else Path(args.project_dir)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    selector_inputs: SelectorInputs = read_selector_file_inputs(args.select_file)
    select: tuple[str, ...] = (*tuple(args.select), *selector_inputs.selectors)
    if args.command == CliCommand.COMPILE:
        return handlers.run_compile(
            CompileCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_cache=args.no_cache,
                defer_to=args.defer_to,
                selected_target=args.target,
                json_output=args.json,
                manifest=args.manifest,
                dag_path=args.dag,
                no_color=args.no_color,
                lineage_mode=CompileLineageMode(args.compile_lineage_mode),
                cli_vars=args.vars,
                profile_flags=CompileProfileFlags(
                    skip_discovery_sql_analysis=args.profile_skip_discovery_sql_analysis,
                    skip_column_inference=args.profile_skip_column_inference,
                    skip_contracts=args.profile_skip_contracts,
                    skip_write=args.profile_skip_write,
                ),
            )
        )
    if args.command == CliCommand.SCOPE:
        return handlers.run_scope(
            request=ScopeCommandRequest(
                project_dir=project_dir,
                target=args.scope_target,
                at=args.scope_at,
                as_path=args.scope_as_path,
                browse=args.scope_browse,
                list_path=args.scope_list,
                defined_under=args.scope_defined_under,
                kinds=tuple(args.scope_kind),
                match=args.scope_match,
                used_only=args.scope_used_only,
                include_nearby=args.scope_include_nearby,
                nearby_depth=args.scope_nearby_depth,
                dependency_depth=args.scope_dependency_depth,
                explain=args.scope_explain,
                globals=args.scope_globals,
                page_size=args.scope_page_size,
                after=args.scope_after,
                paths=args.scope_paths,
                json_output=args.json,
                no_cache=args.no_cache,
            )
        )
    if args.command == CliCommand.DAG:
        return handlers.run_dag(
            project_dir=project_dir,
            no_sql_validation=args.no_sql_validation,
            json_output=args.json,
            cli_vars=args.vars,
        )
    if args.command == CliCommand.PLAN:
        return handlers.run_plan(
            PlanCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_cache=args.no_cache,
                defer_to=args.defer_to,
                defer_sources_to=args.defer_sources_to,
                selected_target=args.target,
                cursor_overrides=CursorOverrides(
                    start_ts=args.start_cursor_ts,
                    end_ts=args.end_cursor_ts,
                    start_int=args.start_cursor_int,
                    end_int=args.end_cursor_int,
                ),
                json_output=args.json,
                full_refresh=args.full_refresh,
                virtual_env=args.virtual_env,
                load_sources=args.load_sources,
                include_python=args.include_python,
                no_color=args.no_color,
                select=select,
                exclude=tuple(args.exclude),
                verbose=args.verbose,
                cli_vars=args.vars,
                include_stale_upstreams=args.include_stale_upstreams,
                changes_only=args.changes_only,
                max_microbatches=args.max_microbatches,
                selection_diagnostics=args.selection_diagnostics,
            )
        )
    if args.command == CliCommand.DBT:
        return _dispatch_dbt_command(
            args=args,
            handlers=handlers,
            project_dir=project_dir,
            effective_project_dir=effective_project_dir,
        )
    if args.command == CliCommand.BUILD:
        return handlers.run_build(
            BuildCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_cache=args.no_cache,
                defer_to=args.defer_to,
                defer_clone_from=args.defer_clone_from,
                defer_sources_to=args.defer_sources_to,
                selected_target=args.target,
                cursor_overrides=CursorOverrides(
                    start_ts=args.start_cursor_ts,
                    end_ts=args.end_cursor_ts,
                    start_int=args.start_cursor_int,
                    end_int=args.end_cursor_int,
                ),
                no_color=args.no_color,
                fail_fast=args.fail_fast,
                full_refresh=args.full_refresh,
                virtual_env=args.virtual_env,
                load_sources=args.load_sources,
                reload_sources=args.reload,
                include_python=args.include_python,
                allow_snapshot_full_refresh=args.allow_snapshot_full_refresh,
                allow_table_type_downgrade=args.allow_table_type_downgrade,
                allow_snapshot_schema_change=args.allow_snapshot_schema_change,
                concurrency=args.concurrency,
                select=select,
                selector_files=selector_inputs.files,
                exclude=tuple(args.exclude),
                verbose=args.verbose,
                debug=args.debug,
                cli_vars=args.vars,
                include_stale_upstreams=args.include_stale_upstreams,
                changes_only=args.changes_only,
                run_tests=args.run_tests,
                run_audits=args.run_audits,
                manifest=args.manifest,
                json_output=args.json,
                json_output_path=args.json_output,
                event_output_path=args.event_output,
                max_microbatches=args.max_microbatches,
                selection_diagnostics=args.selection_diagnostics,
            )
        )
    if args.command == CliCommand.FRESHNESS:
        return handlers.run_freshness(
            FreshnessCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
                fail_on_error=args.fail_on_error,
                compare_state=args.state,
                fail_on_stale=args.fail_on_stale,
                virtual_environment_name=args.virtual_env,
            )
        )
    if args.command == CliCommand.TEST:
        return handlers.run_test(
            TestCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.CHECK:
        return handlers.run_check(
            CheckCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.AUDIT:
        return handlers.run_audit(
            AuditCommandRequest(
                project_dir=project_dir,
                no_sql_validation=args.no_sql_validation,
                defer_to=args.defer_to,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.LOAD:
        return handlers.run_load(
            LoadCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                reload=args.reload,
                concurrency=args.concurrency,
                cursor_overrides=CursorOverrides(
                    start_ts=args.start_cursor_ts,
                    end_ts=args.end_cursor_ts,
                    start_int=args.start_cursor_int,
                    end_int=args.end_cursor_int,
                ),
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.SEED:
        return handlers.run_seed(
            SeedCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                selected_target=args.target,
                select=select,
                exclude=tuple(args.exclude),
                concurrency=args.concurrency,
                cli_vars=args.vars,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.LINEAGE:
        return handlers.run_lineage(
            project_dir=project_dir,
            no_sql_validation=args.no_sql_validation,
            target=args.lineage_target,
            output_format=args.lineage_format,
            direction=args.lineage_direction,
            depth=args.lineage_depth,
            select=select,
            exclude=tuple(args.exclude),
            lineage_mode=ColumnLineageMode(args.lineage_mode),
            cli_vars=args.vars,
        )
    if args.command == CliCommand.CLONE:
        if args.from_target is None:
            raise CliUserError("clone requires --from", code="C406")
        return handlers.run_clone(
            CloneCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                no_sql_validation=args.no_sql_validation,
                origin_target_name=args.from_target,
                destination_target_name=args.to_target,
                hard_copy=args.hard_copy,
                virtual_env=args.virtual_env,
                skip_locked=args.skip_locked,
                select=select,
                exclude=tuple(args.exclude),
                verbose=args.verbose,
                cli_vars=args.vars,
                json_output_path=args.json_output,
                event_output_path=args.event_output,
            )
        )
    if args.command == CliCommand.DIFF:
        from_name: str
        to_name: str
        from_name, to_name = parse_diff_name_range(args.target_range)
        return handlers.run_diff(
            DiffCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                no_sql_validation=args.no_sql_validation,
                from_name=from_name,
                to_name=to_name,
                full=args.full,
                schema_only=args.schema_only,
                bounded=args.bounded,
                max_column_examples=args.max_column_examples,
                max_row_only_examples=args.max_row_only_examples,
                select=select,
                exclude=tuple(args.exclude),
                verbose=args.verbose,
                cli_vars=args.vars,
                allow_partial_diff=args.allow_partial_diff,
            )
        )
    if args.command == CliCommand.RECONCILE:
        return handlers.run_reconcile(
            project_dir=project_dir,
            no_color=args.no_color,
            virtual_environment=args.virtual_env,
            reconcile_command=args.reconcile_command,
            model_name=getattr(args, "reconcile_model", None),
            seed_name=getattr(args, "reconcile_seed", None),
            physical_relation_name=getattr(args, "reconcile_physical_relation", None),
            auto_approve=getattr(args, "auto_approve", False),
            cli_vars=args.vars,
        )
    if args.command == CliCommand.PROMOTE:
        if args.from_virtual_environment is None or args.to_virtual_environment is None:
            raise CliUserError("promote requires --from and --to", code="C244")
        return handlers.run_promote(
            PromoteCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                no_sql_validation=args.no_sql_validation,
                from_virtual_environment=args.from_virtual_environment,
                to_virtual_environment=args.to_virtual_environment,
                select=select,
                exclude=tuple(args.exclude),
                allow_partial_promotion=args.allow_partial_promotion,
                include_stale_upstreams=args.include_stale_upstreams,
                verbose=args.verbose,
                cli_vars=args.vars,
            )
        )
    if args.command == CliCommand.ROLLBACK:
        return handlers.run_rollback(
            RollbackCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                no_sql_validation=args.no_sql_validation,
                virtual_environment=args.virtual_env,
                verbose=args.verbose,
                checkpoint_id=args.rollback_checkpoint_id,
                select=select,
                exclude=tuple(args.exclude),
                allow_partial_rollback=args.allow_partial_rollback,
                include_stale_upstreams=args.include_stale_upstreams,
                cli_vars=args.vars,
            )
        )
    if args.command == CliCommand.QUERY:
        query_limit: int | None = None if args.query_no_limit else args.query_limit
        return handlers.run_query(
            project_dir=project_dir,
            sql=args.query_sql,
            query_file=None if args.query_file is None else Path(args.query_file),
            selected_target=args.target,
            output_format=args.query_format,
            limit=query_limit,
        )
    if args.command == CliCommand.COST:
        return handlers.run_cost(
            CostCommandRequest(
                project_dir=project_dir,
                selector=args.cost_selector,
                no_color=args.no_color,
                limit=args.cost_limit,
                no_limit=args.cost_no_limit,
                sort=args.cost_sort,
                order=args.cost_order,
                since=args.cost_since,
                until=args.cost_until,
                json_output=args.json,
                json_output_path=args.json_output,
            )
        )
    if args.command == CliCommand.DEBUG:
        return handlers.run_debug(
            project_dir=project_dir,
            no_color=args.no_color,
            no_connection=args.no_connection,
            selected_target=args.target,
            json_output=args.json,
        )
    if args.command == CliCommand.JANITOR:
        return handlers.run_janitor(
            JanitorCommandRequest(
                project_dir=project_dir,
                no_color=args.no_color,
                auto_approve=args.auto_approve,
                retention_days=args.retention_days,
                direct_state_history_versions=args.direct_state_history_versions,
            )
        )
    if args.command == CliCommand.STATE:
        if args.state_command is None:
            raise CliUserError("state requires a subcommand such as 'init'", code="C901")
        return handlers.run_state(
            project_dir=project_dir,
            state_command=args.state_command,
            backup_id=args.state_backup_id,
            auto_approve=args.auto_approve,
            no_color=args.no_color,
            checkpoint_command=args.state_checkpoint_command,
            checkpoint_id=args.state_checkpoint_id,
            virtual_environment=args.virtual_env,
            allow_copy=getattr(args, "allow_copy", False),
        )
    return _dispatch_local_command(
        args=args,
        handlers=handlers,
        project_dir=project_dir,
        select=select,
    )


def _dispatch_local_command(
    *,
    args: CliNamespace,
    handlers: CliEntrypointHandlers,
    project_dir: Path | None,
    select: tuple[str, ...],
) -> int:
    if args.command == CliCommand.INIT:
        return handlers.run_init(project_dir)
    if args.command == CliCommand.PLAYGROUND:
        return handlers.run_playground(
            PlaygroundCommandRequest(
                project_dir=project_dir,
                target_path=args.playground_path,
                template=args.playground_template,
            )
        )
    if args.command == CliCommand.SKILLS:
        return handlers.run_skills_update(
            project_dir=project_dir,
            global_install=args.skills_global,
            targets=tuple(args.skills_target),
            force=args.skills_force,
        )
    if args.command == CliCommand.SCENARIO:
        return _dispatch_scenario_command(
            args=args,
            handlers=handlers,
            project_dir=project_dir,
            select=select,
        )
    if args.command == CliCommand.LINT or args.command == CliCommand.FORMAT:
        return _dispatch_lint_format_command(args=args, handlers=handlers, project_dir=project_dir)
    if args.command == CliCommand.KATA:
        return _dispatch_kata_command(args=args, handlers=handlers, project_dir=project_dir)
    return 0


def _dispatch_kata_command(
    *, args: CliNamespace, handlers: CliEntrypointHandlers, project_dir: Path | None
) -> int:
    return handlers.run_kata(
        KataCommandRequest(
            project_dir=project_dir,
            json_output=args.json,
            rule_code=args.kata_rule_code,
            skills=args.kata_command == KATA_SKILLS_COMMAND,
            skills_check=args.kata_skills_check,
            select=tuple(args.select),
            exclude=tuple(args.exclude),
        )
    )


def _dispatch_lint_format_command(
    *,
    args: CliNamespace,
    handlers: CliEntrypointHandlers,
    project_dir: Path | None,
) -> int:
    """Route lint and format commands to their handlers."""

    no_sqruff: bool = getattr(args, "no_sqruff", False)
    if args.command == CliCommand.LINT:
        return handlers.run_lint(project_dir, no_sqruff=no_sqruff)
    return handlers.run_format(project_dir, no_sqruff=no_sqruff)


def _dispatch_dbt_command(
    *,
    args: CliNamespace,
    handlers: CliEntrypointHandlers,
    project_dir: Path | None,
    effective_project_dir: Path,
) -> int:
    if args.dbt_command == DBT_INIT_COMMAND:
        return handlers.run_dbt_init(
            DbtInitCommandRequest(
                cwd=effective_project_dir,
                dbt_project_dir=args.dbt_project_dir,
                profiles_dir=args.dbt_profiles_dir,
                profile_name=args.dbt_profile,
                target_name=args.dbt_target,
                sqb_output_dir=args.sqb_output_dir,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
                skip_dbt_debug=args.skip_dbt_debug,
            )
        )
    if args.dbt_command == DbtInteropCommand.PLAN:
        return handlers.run_dbt_plan(project_dir, tuple(args.dbt_args), args.no_color)
    if args.dbt_command == DbtInteropCommand.RUN:
        return handlers.run_dbt_run(project_dir, tuple(args.dbt_args), args.no_color)
    if args.dbt_command == DbtInteropCommand.BUILD:
        return handlers.run_dbt_build(project_dir, tuple(args.dbt_args), args.no_color)
    if args.dbt_command == DbtInteropCommand.DEBUG:
        return handlers.run_dbt_debug(project_dir, tuple(args.dbt_args), args.no_color)
    raise CliUserError("dbt requires a subcommand such as 'plan'", code="C237")


def _dispatch_scenario_command(
    *,
    args: CliNamespace,
    handlers: CliEntrypointHandlers,
    project_dir: Path | None,
    select: tuple[str, ...],
) -> int:
    scenario_select: tuple[str, ...] = (*tuple(args.scenario_selector), *select)
    if args.scenario_command == SCENARIO_TEST_COMMAND:
        if args.scenario_local and args.scenario_retain:
            raise CliUserError(
                "scenario test --local does not support --retain",
                code=SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
                help=("Local scenario DuckDB files are always kept under target/run/scenarios/."),
            )
        if not args.scenario_local and (args.scenario_sync_snapshots or args.scenario_refresh):
            raise CliUserError(
                "scenario snapshot sync flags require --local",
                code=SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
                help=(
                    "Use sqb scenario test --local --sync-snapshots or "
                    "sqb scenario test --local --refresh."
                ),
            )
        return handlers.run_scenario(
            ScenarioTestCommandRequest(
                project_dir=project_dir,
                no_sql_validation=False,
                no_color=args.no_color,
                selectors=scenario_select,
                exclude=tuple(args.exclude),
                retain=args.scenario_retain,
                local=args.scenario_local,
                strict=args.scenario_strict,
                sync_snapshots=args.scenario_sync_snapshots,
                refresh=args.scenario_refresh,
                limit_inputs=ScenarioSnapshotLimitInputs(
                    max_snapshot_rows=args.scenario_max_snapshot_rows,
                    max_snapshot_total_rows=args.scenario_max_snapshot_total_rows,
                    max_snapshot_bytes=args.scenario_max_snapshot_bytes,
                    max_snapshot_total_bytes=args.scenario_max_snapshot_total_bytes,
                    force=args.scenario_force,
                ),
                json_output=args.json,
                json_output_path=args.json_output,
            ),
        )
    if args.scenario_command == SCENARIO_CAPTURE_COMMAND:
        return handlers.run_scenario_capture(
            ScenarioCaptureCommandRequest(
                project_dir=project_dir,
                no_sql_validation=False,
                no_color=args.no_color,
                selectors=scenario_select,
                exclude=tuple(args.exclude),
                retain=args.scenario_retain,
                limit_inputs=ScenarioSnapshotLimitInputs(
                    max_snapshot_rows=args.scenario_max_snapshot_rows,
                    max_snapshot_total_rows=args.scenario_max_snapshot_total_rows,
                    max_snapshot_bytes=args.scenario_max_snapshot_bytes,
                    max_snapshot_total_bytes=args.scenario_max_snapshot_total_bytes,
                    force=args.scenario_force,
                ),
            ),
        )
    raise CliUserError(
        "scenario requires a subcommand such as 'test'",
        code=SCENARIO_CLI_MISSING_SUBCOMMAND,
    )
