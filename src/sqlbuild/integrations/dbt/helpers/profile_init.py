"""Initialize SQLBuild projects from dbt projects."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.helpers.profile_load import (
    default_profiles_dir,
    load_dbt_project_metadata,
    load_raw_dbt_profile,
    select_dbt_profile_output,
)
from sqlbuild.integrations.dbt.helpers.profile_normalize import normalize_dbt_profile_connection
from sqlbuild.integrations.dbt.helpers.profile_render import render_selected_dbt_profile_output
from sqlbuild.integrations.dbt.models import (
    DbtInitProgressCallbacks,
    DbtInitRequest,
    DbtInitResult,
    DbtProjectProfileMetadata,
    NormalizedDbtProfileConnection,
    ResolvedDbtProfileOutput,
    SelectedDbtProfileOutput,
)


def build_dbt_init_project(*, request: DbtInitRequest) -> DbtInitResult:
    """Create or render a minimal SQLBuild project from a dbt project."""

    dbt_project_dir: Path = _resolve_path(root=request.cwd, path=request.dbt_project_dir)
    profiles_dir: Path = (
        _resolve_path(root=request.cwd, path=request.profiles_dir)
        if request.profiles_dir is not None
        else default_profiles_dir()
    )
    output_dir: Path = (
        _resolve_path(root=request.cwd, path=request.sqb_output_dir)
        if request.sqb_output_dir is not None
        else dbt_project_dir.parent / "sqlbuild_project"
    )
    project_file: Path = output_dir / "sqlbuild_project.toml"
    if project_file.exists() and not request.overwrite:
        raise DbtProfileError(f"{project_file} already exists. Pass --overwrite to replace it.")
    if output_dir.exists() and not output_dir.is_dir():
        raise DbtProfileError(f"SQLBuild output path is not a directory: {output_dir}")

    _start_progress(request.progress_callbacks, "Inspecting dbt project and profile...")
    metadata: DbtProjectProfileMetadata = load_dbt_project_metadata(project_dir=dbt_project_dir)
    profile_name: str = request.profile_name or metadata.profile_name
    selected: SelectedDbtProfileOutput = select_dbt_profile_output(
        profile=load_raw_dbt_profile(profiles_dir=profiles_dir, profile_name=profile_name),
        target_name=request.target_name,
    )
    _complete_progress(request.progress_callbacks, "Inspected dbt project and profile.")

    _start_progress(request.progress_callbacks, "Rendering dbt profile connection...")
    resolved: ResolvedDbtProfileOutput = render_selected_dbt_profile_output(
        selected=selected,
        project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
    )
    normalized: NormalizedDbtProfileConnection = normalize_dbt_profile_connection(resolved=resolved)
    target_path: Path = _resolve_path(root=dbt_project_dir, path=Path(metadata.target_path))
    toml: str = _build_project_toml(
        project_name=metadata.project_name.replace("-", "_"),
        adapter=normalized.adapter,
        target_name=selected.target_name,
        profile_name=profile_name,
        dbt_project_dir=_display_path(path=dbt_project_dir, root=output_dir),
        profiles_dir=_display_path(path=profiles_dir, root=output_dir),
        target_path=_display_path(path=target_path, root=output_dir),
        target_schema=normalized.target_schema,
        target_database=normalized.target_database,
        production_git_ref=request.production_git_ref,
    )
    _complete_progress(request.progress_callbacks, "Rendered dbt profile connection.")
    warnings: list[str] = list(normalized.warnings)
    if not request.skip_dbt_debug:
        _start_progress(request.progress_callbacks, "Running dbt debug...")
        warnings.extend(
            _dbt_debug_warnings(
                dbt_project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_name=selected.target_name,
            )
        )
        _complete_progress(request.progress_callbacks, "Finished dbt debug.")
    if not request.dry_run:
        _start_progress(request.progress_callbacks, "Writing SQLBuild project config...")
        output_dir.mkdir(parents=True, exist_ok=True)
        project_file.write_text(toml, encoding="utf-8")
        macro_file: Path = output_dir / "dbt" / "macros" / "generate_schema_name.sql"
        macro_file.parent.mkdir(parents=True, exist_ok=True)
        if not macro_file.exists() or request.overwrite:
            macro_file.write_text(_default_generate_schema_name_macro(), encoding="utf-8")
        _complete_progress(request.progress_callbacks, "Wrote SQLBuild project config.")
    else:
        macro_file = output_dir / "dbt" / "macros" / "generate_schema_name.sql"
    return DbtInitResult(
        output_dir=output_dir,
        project_file=project_file,
        project_name=metadata.project_name.replace("-", "_"),
        macro_file=macro_file,
        production_git_ref=request.production_git_ref,
        adapter=normalized.adapter,
        target_name=selected.target_name,
        profile_name=profile_name,
        toml=toml,
        warnings=tuple(warnings),
        dry_run=request.dry_run,
    )


def _resolve_path(*, root: Path, path: Path) -> Path:
    expanded: Path = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (root / expanded).resolve()


def _start_progress(callbacks: DbtInitProgressCallbacks, message: str) -> None:
    if callbacks.start is not None:
        callbacks.start(message)


def _complete_progress(callbacks: DbtInitProgressCallbacks, message: str) -> None:
    if callbacks.complete is not None:
        callbacks.complete(message)


def _display_path(*, path: Path, root: Path) -> str:
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:
        pass
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        home: Path = Path.home().resolve()
        try:
            return "~/" + path.relative_to(home).as_posix()
        except ValueError:
            return path.as_posix()


def _build_project_toml(
    *,
    project_name: str,
    adapter: str,
    target_name: str,
    profile_name: str,
    dbt_project_dir: str,
    profiles_dir: str,
    target_path: str,
    target_schema: str | None,
    target_database: str | None,
    production_git_ref: str,
) -> str:
    target_lines: list[str] = [f"[targets.{_quote_key(target_name)}]"]
    if target_database is not None:
        target_lines.append(f'database = "{_escape(target_database)}"')
    if target_schema is not None:
        target_lines.append(f'schema = "{_escape(target_schema)}"')
    target_lines.extend(
        [
            "",
            f"[targets.{_quote_key(target_name)}.connection]",
            'source = "dbt_profile"',
            f'profile = "{_escape(profile_name)}"',
            f'target = "{_escape(target_name)}"',
        ]
    )
    return (
        f'name = "{_escape(project_name)}"\n'
        f'adapter = "{_escape(adapter)}"\n'
        f'default_target = "{_escape(target_name)}"\n\n'
        "[dbt]\n"
        f'project_dir = "{_escape(dbt_project_dir)}"\n'
        f'profiles_dir = "{_escape(profiles_dir)}"\n'
        f'target_path = "{_escape(target_path)}"\n'
        f'target = "{_escape(target_name)}"\n\n'
        "[dbt.reuse_from]\n"
        f'git_ref = "{_escape(production_git_ref)}"\n'
        'generate_schema_name_override = "dbt/macros/generate_schema_name.sql"\n\n'
        + "\n".join(target_lines)
        + "\n"
    )


def _default_generate_schema_name_macro() -> str:
    return (
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n"
        "    {%- if custom_schema_name is none -%}\n"
        "        {{ target.schema }}\n"
        "    {%- else -%}\n"
        "        {{ custom_schema_name | trim }}\n"
        "    {%- endif -%}\n"
        "{%- endmacro %}\n"
    )


def _quote_key(value: str) -> str:
    if value.replace("_", "").replace("-", "").isalnum():
        return value
    return f'"{_escape(value)}"'


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _dbt_debug_warnings(
    *, dbt_project_dir: Path, profiles_dir: Path, target_name: str
) -> tuple[str, ...]:
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            (
                "dbt",
                "debug",
                "--project-dir",
                dbt_project_dir.as_posix(),
                "--profiles-dir",
                profiles_dir.as_posix(),
                "--target",
                target_name,
            ),
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return ("dbt debug was skipped because the dbt executable was not found on PATH.",)
    if result.returncode == 0:
        return ()
    detail: str = (result.stderr or result.stdout).strip()
    if detail:
        return ("dbt debug failed; generated SQLBuild config anyway. " + detail,)
    return ("dbt debug failed; generated SQLBuild config anyway.",)
