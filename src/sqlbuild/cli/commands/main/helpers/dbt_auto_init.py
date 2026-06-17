"""Auto-init support for dbt interop commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.main.helpers.dbt_init.progress import DbtInitProgressReporter
from sqlbuild.cli.commands.main.helpers.dbt_init.prompt import resolve_production_git_ref
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.integrations.dbt.main.profile_init import run_dbt_profile_init
from sqlbuild.integrations.dbt.models import DbtInitProgressCallbacks, DbtInitRequest, DbtInitResult
from sqlbuild.shared.helpers.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color


def ensure_sqlbuild_project_for_dbt_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> tuple[Path, tuple[str, ...]]:
    """Create or resolve the SQLBuild twin project for a dbt interop command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    if (effective_project_dir / PROJECT_CONFIG_FILENAME).exists():
        return effective_project_dir, args

    dbt_project_dir: Path = _resolve_dbt_project_dir(
        effective_project_dir=effective_project_dir,
        args=args,
    )
    twin_project_dir: Path = dbt_project_dir.parent / "sqlbuild_project"
    forwarded_args: tuple[str, ...] = _normalize_forwarded_path_args(
        args=args,
        original_project_dir=effective_project_dir,
    )
    if (twin_project_dir / PROJECT_CONFIG_FILENAME).exists():
        return twin_project_dir, forwarded_args

    use_color: bool = not no_color and "--json" not in args and supports_color()
    progress_stream: TextIO = sys.stderr
    progress: DbtInitProgressReporter = DbtInitProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    production_git_ref: str = resolve_production_git_ref(
        explicit_git_ref=None,
        input_stream=sys.stdin,
        output_stream=progress_stream,
        use_color=use_color,
    )
    result: DbtInitResult = run_dbt_profile_init(
        request=DbtInitRequest(
            cwd=effective_project_dir,
            dbt_project_dir=dbt_project_dir,
            profiles_dir=_optional_path_arg(args=args, flag="--profiles-dir"),
            profile_name=None,
            target_name=_value_arg(args=args, flag="--target"),
            sqb_output_dir=twin_project_dir,
            dry_run=False,
            overwrite=False,
            skip_dbt_debug=True,
            production_git_ref=production_git_ref,
            progress_callbacks=DbtInitProgressCallbacks(
                start=progress.start,
                complete=progress.complete,
            ),
        )
    )
    _render_auto_init_result(result=result, stream=progress_stream, use_color=use_color)
    return result.output_dir, forwarded_args


def _render_auto_init_result(*, result: DbtInitResult, stream: TextIO, use_color: bool) -> None:
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild dbt setup created")
    doc.blank()
    doc.section("Setup summary")
    doc.fields(
        (
            ("Config file", str(result.project_file)),
            ("Production git ref", result.production_git_ref),
            ("Production schema macro", str(result.macro_file)),
        ),
        label_width=25,
    )
    doc.blank()
    doc.line(
        f"{style.value('What SQLBuild created')}: a twin config plus a production "
        "schema macro. The macro lives in the SQLBuild project, not your dbt project."
    )
    doc.line(
        "SQLBuild injects it only while compiling the production git ref so reuse points "
        "at the correct production relations."
    )
    stream.write("\n" + doc.render())


def _resolve_dbt_project_dir(*, effective_project_dir: Path, args: tuple[str, ...]) -> Path:
    raw_project_dir: str | None = _value_arg(args=args, flag="--project-dir")
    dbt_project_dir: Path = (
        Path(raw_project_dir).expanduser() if raw_project_dir is not None else effective_project_dir
    )
    if dbt_project_dir.is_absolute():
        return dbt_project_dir.resolve()
    return (effective_project_dir / dbt_project_dir).resolve()


def _optional_path_arg(*, args: tuple[str, ...], flag: str) -> Path | None:
    raw_value: str | None = _value_arg(args=args, flag=flag)
    if raw_value is None:
        return None
    return Path(raw_value)


def _normalize_forwarded_path_args(
    *, args: tuple[str, ...], original_project_dir: Path
) -> tuple[str, ...]:
    value_path_flags: frozenset[str] = frozenset(
        {"--project-dir", "--profiles-dir", "--target-path"}
    )
    normalized: list[str] = []
    skip_next: bool = False
    index: int
    arg: str
    for index, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        normalized.append(arg)
        if arg not in value_path_flags:
            continue
        if index + 1 >= len(args):
            continue
        normalized.append(
            _resolve_forwarded_path_arg(raw_value=args[index + 1], root=original_project_dir)
        )
        skip_next = True
    return tuple(normalized)


def _resolve_forwarded_path_arg(*, raw_value: str, root: Path) -> str:
    path: Path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve().as_posix()
    return (root / path).resolve().as_posix()


def _value_arg(*, args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]
