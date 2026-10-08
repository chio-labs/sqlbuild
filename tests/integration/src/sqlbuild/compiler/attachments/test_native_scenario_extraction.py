"""Scenario CTEs extract and classify identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.compile.models import CompileSqlScenarioCtes
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    ScenarioParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_scenario,
    native_scenario_answered,
    scenario_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioParityTestCase(
            description="generic syntax",
            seed=20261008,
            count=3000,
            syntax=SqlLexicalSyntax(),
            expected_minimum_extracted=200,
            expected_minimum_native=140,
            expected_minimum_python_errors=2000,
        ),
        ScenarioParityTestCase(
            description="hash comments, which keep the Python scanner",
            seed=20261009,
            count=1000,
            syntax=SqlLexicalSyntax(line_comment_prefixes=frozenset({"--", "#"})),
            expected_minimum_extracted=60,
            expected_minimum_native=30,
            expected_minimum_python_errors=600,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_scenarios_when_extracting_with_preview_then_python_output_matches(
    test_case: ScenarioParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_scenario(rng=rng) for _ in range(test_case.count)]

    python: list[object] = [
        scenario_outcome(
            sql=sql, syntax=test_case.syntax, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch
        )
        for sql in sqls
    ]
    preview: list[object] = [
        scenario_outcome(
            sql=sql,
            syntax=test_case.syntax,
            engine=CompilerEngine.NATIVE_PREVIEW,
            monkeypatch=monkeypatch,
        )
        for sql in sqls
    ]

    assert (
        mismatches(inputs=[*sqls], expected=python, actual=preview),
        sum(isinstance(item, CompileSqlScenarioCtes) for item in python)
        >= test_case.expected_minimum_extracted,
        sum(map(native_scenario_answered, sqls)) >= test_case.expected_minimum_native,
        sum(isinstance(item, str) for item in python) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
