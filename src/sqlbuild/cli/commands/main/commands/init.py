"""Scaffold a new blank SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.init.scaffold import scaffold_blank_project
from sqlbuild.cli.commands._helpers.skills.update import update_sqlbuild_skills
from sqlbuild.presentation.classes.cli_document import CliDocument
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.supports_color import supports_color


def run_init(project_dir: Path | None) -> int:
    """Create a minimal SQLBuild project in the current directory."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    project_file: Path = base_dir / "sqlbuild_project.toml"

    if project_file.exists():
        from sqlbuild.cli.exceptions import CliUserError

        raise CliUserError(
            "sqlbuild_project.toml already exists in this directory",
            code="C900",
        )

    project_name: str = base_dir.name.replace("-", "_").replace(" ", "_").lower()

    _ = scaffold_blank_project(base_dir=base_dir, project_name=project_name)

    _ = update_sqlbuild_skills(project_dir=base_dir)

    use_color: bool = supports_color()
    style: CliStyle = CliStyle(use_color=use_color)
    doc: CliDocument = CliDocument(style)
    doc.header(text="SQLBuild project created")
    doc.blank()
    doc.field(label="Project", value=project_name)
    doc.field(label="Config", value="sqlbuild_project.toml", value_padding="  ")
    doc.blank()
    doc.section("Next steps")
    doc.line("  1. Add sources to sources/")
    doc.line("  2. Add seeds to seeds/ or loaders to loaders/")
    doc.line("  3. Add tasks to tasks/, assets to assets/, or checks to checks/")
    doc.line("  4. Add hooks to hooks/, functions to functions/, or macros to macros/")
    doc.line("  5. Add models to models/staging/ and models/marts/")
    doc.line("  6. Add tests to tests/unit/ or tests/scenarios/")
    doc.command_line(prefix="  7. ", command="sqb compile")
    doc.command_line(prefix="  8. ", command="sqb build")
    print(doc.render(), end="")
    return 0
