"""Scenario CTEs and errors extract identically under the preview engine, mostly natively."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from sqlbuild.compiler.compile.models import CompileSqlScenarioCtes
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    ScenarioParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_scenario,
    native_scenario_answer,
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
            expected_minimum_extracted=150,
            expected_minimum_native=80,
            expected_minimum_python_errors=2000,
            expected_minimum_native_errors=1200,
        ),
        ScenarioParityTestCase(
            description="hash comments under the adapter's rules",
            seed=20261009,
            count=1000,
            syntax=SqlLexicalSyntax(line_comment_prefixes=frozenset({"--", "#"})),
            expected_minimum_extracted=50,
            expected_minimum_native=25,
            expected_minimum_python_errors=600,
            expected_minimum_native_errors=400,
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
    answers: list[str] = [native_scenario_answer(sql=sql, syntax=test_case.syntax) for sql in sqls]
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
        answers.count("extracted") >= test_case.expected_minimum_native,
        sum(isinstance(item, str) for item in python) >= test_case.expected_minimum_python_errors,
        answers.count("error") >= test_case.expected_minimum_native_errors,
    ) == ([], True, True, True, True), (test_case.description, Counter(answers))


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
