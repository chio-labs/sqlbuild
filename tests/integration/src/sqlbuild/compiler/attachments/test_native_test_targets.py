"""Model SQL test targets validate identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.compile.models import CompileModelSqlTestCtes
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    TargetParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_test_targets,
    target_validation_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        TargetParityTestCase(
            description="seeded mocks, macro mocks, expected models and assertion targets",
            seed=20261008,
            count=2000,
            expected_minimum_valid=150,
            expected_minimum_python_errors=1000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_test_targets_when_validating_with_preview_then_python_errors_match(
    test_case: TargetParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    targets: list[tuple[CompileModelSqlTestCtes, tuple[str, ...]]] = [
        generated_test_targets(rng=rng) for _ in range(test_case.count)
    ]

    python: list[str | None] = [
        target_validation_outcome(
            payload=payload,
            assertion_targets=assertion_targets,
            engine=CompilerEngine.PYTHON,
            monkeypatch=monkeypatch,
        )
        for payload, assertion_targets in targets
    ]
    preview: list[str | None] = [
        target_validation_outcome(
            payload=payload,
            assertion_targets=assertion_targets,
            engine=CompilerEngine.NATIVE_PREVIEW,
            monkeypatch=monkeypatch,
        )
        for payload, assertion_targets in targets
    ]

    assert (
        mismatches(inputs=[*targets], expected=[*python], actual=[*preview]),
        python.count(None) >= test_case.expected_minimum_valid,
        len(python) - python.count(None) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
