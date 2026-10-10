"""Run every refactoring test under the shipped engine and the native refactoring stage."""

import pytest

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine


@pytest.fixture(
    autouse=True,
    params=(CompilerEngine.NATIVE, CompilerEngine.NATIVE_PREVIEW),
    ids=lambda engine: engine.value,
)
def refactor_compiler_engine(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> CompilerEngine:
    engine: CompilerEngine = request.param
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine.value)
    return engine
