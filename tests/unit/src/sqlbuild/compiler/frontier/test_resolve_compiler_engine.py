"""The compiler engine switch reads SQLBUILD_COMPILER_ENGINE and rejects unknown values."""

from __future__ import annotations

import os

import pytest

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.exceptions import CompilerEngineError
from sqlbuild.compiler.frontier.main.compiler_engine_override import compiler_engine_override
from sqlbuild.compiler.frontier.main.resolve_compiler_engine import resolve_compiler_engine
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.unit.src.sqlbuild.compiler.frontier._test_types import (
    EngineErrorTestCase,
    EngineOverrideTestCase,
    EngineResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EngineResolutionTestCase(
            description="empty", raw_value="", expected_engine=CompilerEngine.NATIVE
        ),
        EngineResolutionTestCase(
            description="python", raw_value="python", expected_engine=CompilerEngine.PYTHON
        ),
        EngineResolutionTestCase(
            description="native", raw_value="native", expected_engine=CompilerEngine.NATIVE
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_variable_when_resolving_then_returns_selected_engine(
    test_case: EngineResolutionTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.raw_value)

    assert resolve_compiler_engine() is test_case.expected_engine


@pytest.mark.parametrize(
    "test_case",
    [
        EngineResolutionTestCase(
            description="unset", raw_value="", expected_engine=CompilerEngine.NATIVE
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_engine_variable_when_resolving_then_native_is_the_default(
    test_case: EngineResolutionTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(COMPILER_ENGINE_ENV_VAR, raising=False)

    assert resolve_compiler_engine() is test_case.expected_engine


@pytest.mark.parametrize(
    "test_case",
    [
        EngineErrorTestCase(
            description="unknown",
            raw_value="rust",
            expected_message="SQLBUILD_COMPILER_ENGINE must be one of python, native (got 'rust')",
        ),
        EngineErrorTestCase(
            description="wrong_case",
            raw_value="Native",
            expected_message=(
                "SQLBUILD_COMPILER_ENGINE must be one of python, native (got 'Native')"
            ),
        ),
        EngineErrorTestCase(
            description="padded",
            raw_value=" python",
            expected_message=(
                "SQLBUILD_COMPILER_ENGINE must be one of python, native (got ' python')"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_engine_when_resolving_then_error_names_accepted_and_current_values(
    test_case: EngineErrorTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.raw_value)

    with pytest.raises(CompilerEngineError) as error:
        _ = resolve_compiler_engine()

    assert str(error.value) == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    [
        EngineOverrideTestCase(
            description="python_restored",
            previous="python",
            override=CompilerEngine.NATIVE,
            expected_inside=CompilerEngine.NATIVE,
            expected_after="python",
        ),
        EngineOverrideTestCase(
            description="empty_restored",
            previous="",
            override=CompilerEngine.NATIVE,
            expected_inside=CompilerEngine.NATIVE,
            expected_after="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_override_when_leaving_then_engine_variable_is_restored(
    test_case: EngineOverrideTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.previous)

    with compiler_engine_override(test_case.override):
        inside: CompilerEngine = resolve_compiler_engine()

    assert inside is test_case.expected_inside
    assert os.environ[COMPILER_ENGINE_ENV_VAR] == test_case.expected_after


@pytest.mark.parametrize(
    "test_case",
    [
        EngineOverrideTestCase(
            description="unset_removed",
            previous="",
            override=CompilerEngine.NATIVE,
            expected_inside=CompilerEngine.NATIVE,
            expected_after="<unset>",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unset_variable_when_override_ends_then_variable_is_removed(
    test_case: EngineOverrideTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(COMPILER_ENGINE_ENV_VAR, raising=False)

    with compiler_engine_override(test_case.override):
        inside: CompilerEngine = resolve_compiler_engine()

    assert inside is test_case.expected_inside
    assert os.environ.get(COMPILER_ENGINE_ENV_VAR, "<unset>") == test_case.expected_after


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
