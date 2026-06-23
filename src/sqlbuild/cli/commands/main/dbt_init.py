"""CLI dbt init command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.dbt_init.branch_detection import (
    detect_default_production_git_ref,
)
from sqlbuild.cli.commands.main.helpers.dbt_init.progress import DbtInitProgressReporter
from sqlbuild.cli.commands.main.helpers.dbt_init.prompt import resolve_production_git_ref
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.integrations.dbt.main.profile_init import (
    run_dbt_profile_init,
    validate_dbt_profile_init_request,
)
from sqlbuild.integrations.dbt.models import (
    DbtInitProgressCallbacks,
    DbtInitRequest,
    DbtInitResult,
)
from sqlbuild.shared.helpers.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_init_command(
    *,
    cwd: Path,
    dbt_project_dir: str | None,
    profiles_dir: str | None,
    profile_name: str | None,
    target_name: str | None,
    sqb_output_dir: str | None,
    dry_run: bool,
    overwrite: bool,
    skip_dbt_debug: bool,
    production_git_ref: str | None = None,
) -> int:
    """Execute SQLBuild-owned `sqb dbt init`."""

    resolved_dbt_project_dir: Path | None = (
        None if dbt_project_dir is None else Path(dbt_project_dir)
    )
    if resolved_dbt_project_dir is None and (cwd / "dbt_project.yml").exists():
        resolved_dbt_project_dir = Path(".")
    if resolved_dbt_project_dir is None:
        raise CliUserError(
            "sqb dbt init requires --project-dir pointing at a dbt project",
            code="C242",
        )
    use_color: bool = supports_color()
    progress: DbtInitProgressReporter = DbtInitProgressReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    base_request: DbtInitRequest = DbtInitRequest(
        cwd=cwd,
        dbt_project_dir=resolved_dbt_project_dir,
        profiles_dir=None if profiles_dir is None else Path(profiles_dir),
        profile_name=profile_name,
        target_name=target_name,
        sqb_output_dir=None if sqb_output_dir is None else Path(sqb_output_dir),
        dry_run=dry_run,
        overwrite=overwrite,
        skip_dbt_debug=skip_dbt_debug,
    )
    validate_dbt_profile_init_request(request=base_request)
    resolved_production_git_ref: str = resolve_production_git_ref(
        explicit_git_ref=production_git_ref,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
        use_color=use_color,
        default_ref=detect_default_production_git_ref(git_probe_dir=cwd / resolved_dbt_project_dir),
    )
    result: DbtInitResult = run_dbt_profile_init(
        request=DbtInitRequest(
            cwd=cwd,
            dbt_project_dir=base_request.dbt_project_dir,
            profiles_dir=base_request.profiles_dir,
            profile_name=base_request.profile_name,
            target_name=base_request.target_name,
            sqb_output_dir=base_request.sqb_output_dir,
            dry_run=base_request.dry_run,
            overwrite=base_request.overwrite,
            skip_dbt_debug=base_request.skip_dbt_debug,
            production_git_ref=resolved_production_git_ref,
            progress_callbacks=(
                DbtInitProgressCallbacks(
                    start=progress.start,
                    complete=progress.complete,
                )
            ),
        )
    )
    if dry_run:
        print("\n" + _render_dbt_init_dry_run(result=result, use_color=use_color), end="")
        return 0
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild project created")
    doc.blank()
    doc.section("Setup summary")
    doc.fields(
        (
            ("Project", result.project_name),
            ("Config file", str(result.project_file)),
            ("Production git ref", result.production_git_ref),
            ("Production schema macro", str(result.macro_file)),
            ("Adapter", result.adapter),
            ("Target", result.target_name),
            ("Profile", result.profile_name),
        ),
        label_width=25,
    )
    doc.blank()
    doc.section("What SQLBuild created")
    doc.line(
        f"  1. {style.value('SQLBuild twin config')} ({style.object_name('sqlbuild_project.toml')})"
    )
    doc.line("     This points SQLBuild at your dbt project and profile. Edit it if dbt paths,")
    doc.line("     profile targets, or reuse settings need to change.")
    doc.line(
        f"  2. {style.value('Production schema macro')} "
        f"({style.object_name('sqlbuild_project/dbt/macros/generate_schema_name.sql')})"
    )
    doc.line("     This file lives in the SQLBuild project, not your dbt project.")
    doc.line("     SQLBuild injects it only while compiling your production git ref for reuse.")
    doc.line("     It must make dbt resolve models to production schemas, because SQLBuild uses")
    doc.line("     those relation names when copying already-built prod tables.")
    doc.blank()
    doc.section("Next steps")
    doc.command_line("  1. ", f"cd {result.output_dir}")
    doc.line("  2. " + style.warning("Review the config file and production schema macro above."))
    doc.command_line("  3. ", "sqb dbt debug")
    doc.command_line("  4. ", "sqb dbt build")
    print("\n" + doc.render(), end="")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _render_dbt_init_dry_run(*, result: DbtInitResult, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild project preview")
    doc.blank()
    doc.field("Project", result.project_name)
    doc.field("Config file", str(result.project_file), value_padding="  ")
    doc.field("Production git ref", result.production_git_ref)
    doc.field("Production schema macro", str(result.macro_file))
    doc.field("Adapter", result.adapter)
    doc.field("Target", result.target_name, value_padding="  ")
    doc.field("Profile", result.profile_name)
    doc.blank()
    doc.section("Generated config")
    doc.line(result.toml.rstrip())
    return doc.render()
