"""Pure orchestration for dbt interop plan inputs."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompileSqlReference,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.manifest import resolve_dbt_manifest_model
from sqlbuild.integrations.dbt.helpers.plan import build_dbt_interop_plan
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.selection import resolve_dbt_interop_sqlbuild_selection
from sqlbuild.integrations.dbt.helpers.selector_terms import dbt_fqn_selector_term
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsResult,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction
from sqlbuild.shared.types import SqlReferenceKind


def plan_dbt_interop_command(
    *,
    command: DbtInteropCommand | str,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    dbt_runner: DbtRunner,
    dbt_options: DbtCliOptions,
    select: Sequence[str],
    exclude: Sequence[str] = (),
    dbt_command_args: Sequence[str] = (),
    sqlbuild_command_args: Sequence[str] = (),
    dbt_executable: str = "dbt",
    sqlbuild_executable: str = "sqb",
) -> DbtInteropPlan:
    """Plan dbt and SQLBuild work from already-compiled interop inputs."""

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
        graph=graph,
        select=select,
        exclude=exclude,
        dbt_anchor_unique_ids_by_term=anchors_by_term,
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
    if not term.endswith("+"):
        return False
    core: str = term.removeprefix("+").removesuffix("+")
    return not _matches_sqlbuild_direct_selector(term=core, project=project)


def _raise_for_dbt_ls_failure(result: DbtLsResult) -> None:
    if result.command.returncode == 0:
        return
    raise DbtInteropRuntimeError("dbt ls failed", help=_dbt_failure_detail(result))


def _dbt_failure_detail(result: DbtLsResult) -> str | None:
    detail: str = (result.command.stderr or result.command.stdout).strip()
    return detail or None


def _matches_sqlbuild_direct_selector(*, term: str, project: CompiledProject) -> bool:
    model_names: frozenset[str] = frozenset(model.name for model in project.models)
    if term in model_names:
        return True
    if term.startswith("tag:"):
        tag: str = term.removeprefix("tag:")
        return any(
            tag in _as_string_tuple(model.config.values.get("tags")) for model in project.models
        )
    if term.startswith("path:"):
        raw_path: str = term.removeprefix("path:")
        translated_path: str = _translate_dbt_path_selector(raw_path)
        return any(
            _model_path_selector(model) == translated_path
            or _model_path_selector(model).startswith(f"{translated_path}/")
            for model in project.models
        )
    return False


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
    selected_names: frozenset[str] = frozenset(selected_model_names)
    terms: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if model.name not in selected_names:
            continue
        reference: CompileSqlReference
        for reference in model.references:
            if reference.ref_kind != SqlReferenceKind.DBT_REF:
                continue
            dbt_model: DbtManifestModel = resolve_dbt_manifest_model(
                manifest=manifest,
                package_name=reference.ref_package,
                name=reference.ref_name,
            )
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
    argv: tuple[str, ...] = _append_dbt_options((dbt_executable, dbt_command), options=options)
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
        core: str = term.removeprefix("+").removesuffix("+")
        if core == "test_type:data":
            has_data_selector = True
        elif core == "test_type:unit":
            has_unit_selector = True
    if has_data_selector and not has_unit_selector:
        return (DbtInteropSqlbuildTestAction.AUDIT,)
    if has_unit_selector and not has_data_selector:
        return (DbtInteropSqlbuildTestAction.TEST,)
    return (DbtInteropSqlbuildTestAction.TEST, DbtInteropSqlbuildTestAction.AUDIT)


def _translate_dbt_path_selector(raw_path: str) -> str:
    return raw_path.replace("\\", "/")


def _model_path_selector(model: CompiledModel) -> str:
    return model.relative_path.parent.as_posix()


def _as_string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, tuple):
        return tuple(str(item) for item in value)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _append_dbt_options(argv: tuple[str, ...], *, options: DbtCliOptions) -> tuple[str, ...]:
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
