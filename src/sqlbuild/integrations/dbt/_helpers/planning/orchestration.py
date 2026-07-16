"""Pure orchestration for dbt interop plan inputs."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.compiler.compile.models import (
    CompiledProject,
)
from sqlbuild.compiler.planner.main.selection.selector_expansion import split_selector_expansion
from sqlbuild.compiler.planner.main.selection.sqlbuild_model_selectors import (
    resolve_sqlbuild_model_selector_names,
)
from sqlbuild.compiler.planner.models import SelectorExpansion
from sqlbuild.integrations.dbt._helpers.manifest.sqlbuild_refs import (
    resolve_sqlbuild_model_dbt_refs,
)
from sqlbuild.integrations.dbt._helpers.planning.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt._helpers.selection.core import resolve_dbt_interop_sqlbuild_selection
from sqlbuild.integrations.dbt._helpers.selection.selector_terms import dbt_fqn_selector_term
from sqlbuild.integrations.dbt._helpers.selection.sql_test_targets import (
    resolve_dbt_sql_test_target_names,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.constants import DBT_PATH_SELECTOR_SEPARATOR
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtInteropCommandArgs,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsResult,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction

_DBT_DATA_TEST_SELECTOR: str = "test_type:data"
_DBT_UNIT_TEST_SELECTOR: str = "test_type:unit"


def plan_dbt_interop_command(
    *,
    command: DbtInteropCommand | str,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    dbt_runner: DbtRunner,
    dbt_options: DbtCliOptions,
    command_args: DbtInteropCommandArgs,
) -> DbtInteropPlan:
    """Plan dbt and SQLBuild work from already-compiled interop inputs."""

    select: Sequence[str] = command_args.select
    exclude: Sequence[str] = command_args.exclude
    dbt_command_args: Sequence[str] = command_args.dbt_command_args
    sqlbuild_command_args: Sequence[str] = command_args.sqlbuild_command_args
    dbt_executable: str = command_args.dbt_executable
    sqlbuild_executable: str = command_args.sqlbuild_executable
    normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    full_dbt_ls: DbtLsResult = dbt_runner.ls(
        options=dbt_options,
        select=select,
        exclude=exclude,
    )
    _raise_for_dbt_ls_failure(full_dbt_ls)
    anchors_by_term: dict[str, tuple[str, ...]] = {}
    term: str
    for term in select:
        if not _is_dbt_anchor_term(term=term, project=project):
            continue
        anchor_ls: DbtLsResult = dbt_runner.ls(
            options=dbt_options,
            select=(term,),
            exclude=exclude,
        )
        _raise_for_dbt_ls_failure(anchor_ls)
        anchors_by_term[term] = tuple(node.unique_id for node in anchor_ls.nodes)

    selection: DbtInteropSelectionResult = resolve_dbt_interop_sqlbuild_selection(
        project=project,
        manifest=manifest,
        graph=graph,
        select=select,
        exclude=exclude,
        dbt_anchor_unique_ids_by_term=anchors_by_term,
    )
    if normalized_command == DbtInteropCommand.TEST:
        dbt_test_target_names: tuple[str, ...] = resolve_dbt_sql_test_target_names(
            project=project,
            manifest=manifest,
            selected_dbt_unique_ids=tuple(node.unique_id for node in full_dbt_ls.nodes),
            select=tuple(select),
        )
        if dbt_test_target_names:
            selection = DbtInteropSelectionResult(
                sqlbuild_model_names=tuple(
                    dict.fromkeys((*selection.sqlbuild_model_names, *dbt_test_target_names))
                ),
                dbt_required_unique_ids=selection.dbt_required_unique_ids,
                dbt_anchor_terms=selection.dbt_anchor_terms,
                dbt_anchor_unique_ids_by_term=selection.dbt_anchor_unique_ids_by_term,
                path_translations=selection.path_translations,
            )
    dbt_required_selector_terms: tuple[str, ...] = _build_required_dbt_selector_terms(
        project=project,
        manifest=manifest,
        selected_model_names=selection.sqlbuild_model_names,
        required_unique_ids=selection.dbt_required_unique_ids,
    )
    supplemental_dbt_argvs: tuple[tuple[str, ...], ...] = _build_supplemental_dbt_argvs(
        command=normalized_command,
        dbt_executable=dbt_executable,
        options=dbt_options,
        selector_terms=dbt_required_selector_terms,
    )
    return build_dbt_interop_plan(
        command=normalized_command,
        dbt_command_argv=_build_primary_dbt_argv(
            command=normalized_command,
            dbt_executable=dbt_executable,
            dbt_command_args=dbt_command_args,
        ),
        dbt_ls_nodes=full_dbt_ls.nodes,
        sqlbuild_command_argvs=_build_sqlbuild_argvs(
            command=normalized_command,
            sqlbuild_executable=sqlbuild_executable,
            select=select,
            selected_model_names=selection.sqlbuild_model_names,
            sqlbuild_command_args=sqlbuild_command_args,
        ),
        selection=selection,
        dbt_required_selector_terms=dbt_required_selector_terms,
        supplemental_dbt_command_argvs=supplemental_dbt_argvs,
    )


def _is_dbt_anchor_term(*, term: str, project: CompiledProject) -> bool:
    parsed: SelectorExpansion = split_selector_expansion(term)
    if not parsed.downstream:
        return False
    if DBT_PATH_SELECTOR_SEPARATOR in parsed.core:
        return False
    return not _matches_sqlbuild_direct_selector(term=parsed.core, project=project)


def _raise_for_dbt_ls_failure(result: DbtLsResult) -> None:
    if result.command.returncode == 0:
        return
    raise DbtInteropRuntimeError("dbt ls failed", help=_dbt_failure_detail(result))


def _dbt_failure_detail(result: DbtLsResult) -> str | None:
    detail: str = (result.command.stderr or result.command.stdout).strip()
    return detail or None


def _matches_sqlbuild_direct_selector(*, term: str, project: CompiledProject) -> bool:
    model_names, _translated_path = resolve_sqlbuild_model_selector_names(
        project=project,
        term=term,
    )
    return bool(model_names)


def _build_required_dbt_selector_terms(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_model_names: Sequence[str],
    required_unique_ids: Sequence[str],
) -> tuple[str, ...]:
    required_ids: frozenset[str] = frozenset(required_unique_ids)
    if not required_ids:
        return ()
    terms: set[str] = set()
    for _model, dbt_model in resolve_sqlbuild_model_dbt_refs(
        project=project,
        manifest=manifest,
        selected_model_names=selected_model_names,
    ):
        if dbt_model.unique_id not in required_ids:
            continue
        selector_term: str = dbt_fqn_selector_term(
            fqn=dbt_model.fqn,
            fallback=dbt_model.name,
        )
        terms.add(f"+{selector_term}")
    return tuple(sorted(terms))


def _build_supplemental_dbt_argvs(
    *,
    command: DbtInteropCommand,
    dbt_executable: str,
    options: DbtCliOptions,
    selector_terms: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    if command == DbtInteropCommand.TEST:
        return ()
    if not selector_terms:
        return ()
    dbt_command: str = "ls" if command == DbtInteropCommand.PLAN else command.value
    argv: tuple[str, ...] = _append_dbt_options(argv=(dbt_executable, dbt_command), options=options)
    return ((*argv, "--select", *selector_terms),)


def _build_primary_dbt_argv(
    *, command: DbtInteropCommand, dbt_executable: str, dbt_command_args: Sequence[str]
) -> tuple[str, ...]:
    dbt_command: str = "ls" if command == DbtInteropCommand.PLAN else command.value
    return (dbt_executable, dbt_command, *dbt_command_args)


def _build_sqlbuild_argvs(
    *,
    command: DbtInteropCommand,
    sqlbuild_executable: str,
    select: Sequence[str],
    selected_model_names: Sequence[str],
    sqlbuild_command_args: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    if not selected_model_names:
        return ()
    if command == DbtInteropCommand.TEST:
        return tuple(
            (
                sqlbuild_executable,
                action.value,
                "--select",
                *selected_model_names,
                *sqlbuild_command_args,
            )
            for action in resolve_sqlbuild_test_actions(select=select)
        )
    sqlbuild_command: tuple[str, ...] = (
        ("build", "--no-tests", "--no-audits")
        if command == DbtInteropCommand.RUN
        else (command.value,)
    )
    return (
        (
            sqlbuild_executable,
            *sqlbuild_command,
            "--select",
            *selected_model_names,
            *sqlbuild_command_args,
        ),
    )


def resolve_sqlbuild_test_actions(
    *, select: Sequence[str]
) -> tuple[DbtInteropSqlbuildTestAction, ...]:
    """Map dbt test-type selectors to SQLBuild validation actions."""

    has_data_selector: bool = False
    has_unit_selector: bool = False
    term: str
    for term in select:
        parsed: SelectorExpansion = split_selector_expansion(term)
        if parsed.core == _DBT_DATA_TEST_SELECTOR:
            has_data_selector = True
        elif parsed.core == _DBT_UNIT_TEST_SELECTOR:
            has_unit_selector = True
    if has_data_selector and not has_unit_selector:
        return (DbtInteropSqlbuildTestAction.AUDIT,)
    if has_unit_selector and not has_data_selector:
        return (DbtInteropSqlbuildTestAction.TEST,)
    return (DbtInteropSqlbuildTestAction.TEST, DbtInteropSqlbuildTestAction.AUDIT)


def _append_dbt_options(*, argv: tuple[str, ...], options: DbtCliOptions) -> tuple[str, ...]:
    if options.project_dir is not None:
        argv = (*argv, "--project-dir", str(options.project_dir))
    if options.profiles_dir is not None:
        argv = (*argv, "--profiles-dir", str(options.profiles_dir))
    if options.target is not None:
        argv = (*argv, "--target", options.target)
    if options.target_path is not None:
        argv = (*argv, "--target-path", str(options.target_path))
    if options.vars is not None:
        argv = (*argv, "--vars", options.vars)
    if options.state is not None:
        argv = (*argv, "--state", str(options.state))
    if options.defer:
        argv = (*argv, "--defer")
    return argv
