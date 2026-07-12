"""Output rendering for the dbt init command."""

from __future__ import annotations

import sys

from sqlbuild.cli.commands.helpers.dbt_init.models import DbtInitCommandRequest
from sqlbuild.integrations.dbt.models import DbtInitResult
from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle


def write_dbt_init_completion_output(
    *, request: DbtInitCommandRequest, result: DbtInitResult, use_color: bool
) -> None:
    """Write dbt init preview or completion output."""

    if request.dry_run:
        print("\n" + _render_dbt_init_dry_run(result=result, use_color=use_color), end="")
        return
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header(text="SQLBuild project created")
    doc.blank()
    doc.section("Setup summary")
    doc.fields(
        rows=(
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
    doc.command_line(prefix="  1. ", command=f"cd {result.output_dir}")
    doc.line("  2. " + style.warning("Review the config file and production schema macro above."))
    doc.command_line(prefix="  3. ", command="sqb dbt debug")
    doc.command_line(prefix="  4. ", command="sqb dbt build")
    print("\n" + doc.render(), end="")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)


def resolve_dbt_init_exit_code(result: DbtInitResult) -> int:
    """Resolve the CLI exit code for dbt init."""

    return 0


def _render_dbt_init_dry_run(*, result: DbtInitResult, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header(text="SQLBuild project preview")
    doc.blank()
    doc.field(label="Project", value=result.project_name)
    doc.field(label="Config file", value=str(result.project_file), value_padding="  ")
    doc.field(label="Production git ref", value=result.production_git_ref)
    doc.field(label="Production schema macro", value=str(result.macro_file))
    doc.field(label="Adapter", value=result.adapter)
    doc.field(label="Target", value=result.target_name, value_padding="  ")
    doc.field(label="Profile", value=result.profile_name)
    doc.blank()
    doc.section("Generated config")
    doc.line(result.toml.rstrip())
    return doc.render()
