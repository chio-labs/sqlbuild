from __future__ import annotations

import pytest

from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from tests.unit.src.sqlbuild.shared.helpers._test_types import CliDocumentTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CliDocumentTestCase(
            description="renders simple document without color",
            use_color=False,
            expected_rendered=(
                "Title\n"
                "\n"
                "  Project: demo\n"
                "  Config:  sqlbuild_project.toml\n"
                "\n"
                "Next steps:\n"
                "  1. Add sources\n"
                "  2. sqb compile\n"
                "\n"
                "Objects:\n"
                "  model_a\n"
                "  model_b\n"
                "Try:\n"
                "  sqb build\n"
            ),
        ),
        CliDocumentTestCase(
            description="renders simple document with semantic color",
            use_color=True,
            expected_rendered=(
                "\033[32m\033[1mTitle\033[0m\n"
                "\n"
                "  \033[34m\033[1mProject\033[0m: demo\n"
                "  \033[34m\033[1mConfig\033[0m:  sqlbuild_project.toml\n"
                "\n"
                "\033[1mNext steps\033[0m:\n"
                "  1. Add sources\n"
                "  2. \033[2msqb compile\033[0m\n"
                "\n"
                "\033[1mObjects\033[0m:\n"
                "  \033[34m\033[1mmodel_a\033[0m\n"
                "  \033[34m\033[1mmodel_b\033[0m\n"
                "\033[32m\033[1mTry\033[0m:\n"
                "\033[2m  \033[0msqb build\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cli_document_when_rendering_simple_output_then_returns_expected_text(
    test_case: CliDocumentTestCase,
) -> None:
    doc: CliDocument = CliDocument(CliStyle(use_color=test_case.use_color))

    doc.header("Title")
    doc.blank()
    doc.field("Project", "demo")
    doc.field("Config", "sqlbuild_project.toml", value_padding="  ")
    doc.blank()
    doc.section("Next steps")
    doc.line("  1. Add sources")
    doc.command_line("  2. ", "sqb compile")
    doc.blank()
    doc.section("Objects")
    doc.items(("model_a", "model_b"))
    doc.title_section("Try")
    doc.commands(("sqb build",), style_command=False)

    assert doc.render() == test_case.expected_rendered


@pytest.mark.parametrize(
    "test_case",
    [
        CliDocumentTestCase(
            description="renders aligned fields and numbered commands",
            use_color=False,
            expected_rendered=(
                "Summary  dev\n"
                "  target status   finalized\n"
                "  promoted models 3\n"
                "Commands:\n"
                "  1. sqb compile\n"
                "  2. sqb build\n"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cli_document_when_rendering_compound_helpers_then_returns_expected_text(
    test_case: CliDocumentTestCase,
) -> None:
    doc: CliDocument = CliDocument(CliStyle(use_color=test_case.use_color))

    doc.header("Summary", suffix="dev")
    doc.fields(
        (
            ("target status", "finalized"),
            ("promoted models", "3"),
        ),
        label_width=15,
    )
    doc.section("Commands")
    doc.commands(("sqb compile", "sqb build"), numbered=True)

    assert doc.render() == test_case.expected_rendered
