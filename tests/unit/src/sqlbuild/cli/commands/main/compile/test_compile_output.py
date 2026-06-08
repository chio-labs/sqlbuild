from __future__ import annotations

import json

import pytest

from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.output import (
    format_compile_json,
    format_compile_text,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileJsonExecutionLayersTestCase,
    CompileTextColorTestCase,
    CompileTextOutputTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    build_compile_output_graph,
    build_compile_output_model_names,
    build_linear_compile_output_graph,
)

TEST_CASES: tuple[CompileTextOutputTestCase, ...] = (
    CompileTextOutputTestCase(
        description="aligns long names and pluralizes singular resource counts",
        model_count=3,
        expected_fragments=(
            "Compile ready (3 models)",
            "  short                                            OK 0 columns",
            "  hourly_activity_with_daily_context               OK 0 columns",
            "  extremely_long_model_name_that_should_be_trun... OK 0 columns",
            "  Compiled: 3 models, 0 seeds, 0 functions, 0 errors, 0 warnings",
        ),
    ),
    CompileTextOutputTestCase(
        description="caps human model list and leaves json guidance",
        model_count=101,
        expected_fragments=(
            "Compile ready (101 models)",
            "  Showing 100 of 101 models.",
            "  Use --json for the full compile report.",
            "  Compiled: 101 models, 0 seeds, 0 functions, 0 errors, 0 warnings",
        ),
        unexpected_fragments=("model_100",),
    ),
)


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_compiled_project_when_formatting_compile_text_then_matches_expected_shape(
    test_case: CompileTextOutputTestCase,
) -> None:
    graph: ProjectGraph = build_compile_output_graph(
        model_names=build_compile_output_model_names(test_case.model_count)
    )
    output: str = format_compile_text(
        graph=graph,
        written=WrittenTarget(
            model_count=test_case.model_count,
            seed_count=0,
            function_count=0,
            audit_count=0,
            test_count=0,
            target_dir=graph.project.models[0].relative_path.parent.parent / "target",
        ),
        manifest=False,
        lineage=None,
        diagnostics=(),
        use_color=False,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output
    assert "\033[" not in output


@pytest.mark.parametrize(
    "test_case",
    [
        CompileJsonExecutionLayersTestCase(
            description="counts deep linear graph layers without recursion",
            model_count=1100,
            expected_execution_layers=1100,
        )
    ],
    ids=["counts deep linear graph layers without recursion"],
)
def test_given_deep_linear_project_when_formatting_compile_json_then_counts_execution_layers(
    test_case: CompileJsonExecutionLayersTestCase,
) -> None:
    graph: ProjectGraph = build_linear_compile_output_graph(model_count=test_case.model_count)

    output: str = format_compile_json(
        graph=graph,
        written=WrittenTarget(
            model_count=test_case.model_count,
            seed_count=0,
            function_count=0,
            audit_count=0,
            test_count=0,
            target_dir=graph.project.models[0].relative_path.parent.parent / "target",
        ),
        manifest=False,
        timings_ms={},
        lineage=None,
        diagnostics=(),
    )
    payload: dict[str, object] = json.loads(output)
    summary: object = payload["summary"]

    assert isinstance(summary, dict)
    assert summary["execution_layers"] == test_case.expected_execution_layers


@pytest.mark.parametrize(
    "test_case",
    [
        CompileTextColorTestCase(
            description="styles compile summary and model rows semantically",
            expected_fragments=(
                "\033[32m\033[1mCompile ready (3 models)\033[0m",
                "\033[34m\033[1mshort",
                "\033[32mOK\033[0m",
                "\033[2m0 columns\033[0m",
                "\033[32m\033[1mCompiled:\033[0m",
                "\033[2mWrote:\033[0m",
            ),
        ),
    ],
    ids=["styles compile summary and model rows semantically"],
)
def test_given_compiled_project_when_formatting_compile_text_with_color_then_styles_semantic_parts(
    test_case: CompileTextColorTestCase,
) -> None:
    graph: ProjectGraph = build_compile_output_graph(
        model_names=build_compile_output_model_names(3)
    )
    output: str = format_compile_text(
        graph=graph,
        written=WrittenTarget(
            model_count=3,
            seed_count=0,
            function_count=0,
            audit_count=0,
            test_count=0,
            target_dir=graph.project.models[0].relative_path.parent.parent / "target",
        ),
        manifest=False,
        lineage=None,
        diagnostics=(),
        use_color=True,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in output
