"""Compile reuse never replays a compile recorded by the other compiler engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.compile_reuse._helpers.attempt import attempt_reuse
from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers._test_types import (
    EngineReuseDigestTestCase,
    EngineReuseStoreTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers.helpers import (
    engine_reuse_key,
    orders_reuse_request,
    write_file,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EngineReuseDigestTestCase(
            description="python_then_native",
            first_environment={COMPILER_ENGINE_ENV_VAR: "python"},
            second_environment={COMPILER_ENGINE_ENV_VAR: "native"},
            expected_same_digest=False,
        ),
        EngineReuseDigestTestCase(
            description="unset_then_python",
            first_environment={},
            second_environment={COMPILER_ENGINE_ENV_VAR: "python"},
            expected_same_digest=False,
        ),
        EngineReuseDigestTestCase(
            description="unset_then_explicit_native",
            first_environment={},
            second_environment={COMPILER_ENGINE_ENV_VAR: "native"},
            expected_same_digest=True,
        ),
        EngineReuseDigestTestCase(
            description="native_twice",
            first_environment={COMPILER_ENGINE_ENV_VAR: "native"},
            second_environment={COMPILER_ENGINE_ENV_VAR: "native"},
            expected_same_digest=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_same_invocation_when_engine_environment_changes_then_reuse_key_follows_engine(
    test_case: EngineReuseDigestTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first: bytes = engine_reuse_key(
        environment=test_case.first_environment, project_dir=tmp_path, monkeypatch=monkeypatch
    )
    second: bytes = engine_reuse_key(
        environment=test_case.second_environment, project_dir=tmp_path, monkeypatch=monkeypatch
    )

    assert (first == second) is test_case.expected_same_digest


@pytest.mark.parametrize(
    "test_case",
    [
        EngineReuseStoreTestCase(
            description="python",
            engine="python",
            expected_entry_directory="target/cache/compiler/project-reuse-v2",
        ),
        EngineReuseStoreTestCase(
            description="native",
            engine="native",
            expected_entry_directory="target/cache/compiler-native-v1/project-reuse-v2",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_attempting_reuse_then_entry_lives_in_that_engine_store(
    test_case: EngineReuseStoreTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path / "sqlbuild_project.toml", 'name = "orders"\nadapter = "duckdb"\n')
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine)
    monkeypatch.setenv(REUSE_DISABLE_ENV_VAR, "0")

    attempt: CompileReuseAttempt = attempt_reuse(request=orders_reuse_request(tmp_path))

    assert attempt.entry_path is not None
    assert attempt.entry_path.parent.relative_to(tmp_path).as_posix() == (
        test_case.expected_entry_directory
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
