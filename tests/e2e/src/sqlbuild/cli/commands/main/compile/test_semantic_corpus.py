"""Single-change semantic probes exercised through the real CLI and DuckDB."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import SemanticCorpusCase
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_semantic_corpus_project,
    semantic_corpus_cases,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [SemanticCorpusCase(**case) for case in semantic_corpus_cases(group="invalid")],
    ids=lambda case: case.description,
)
def test_given_invalid_semantics_when_compiling_then_errors_precede_execution(
    test_case: SemanticCorpusCase,
    semantic_playground: Path,
    tmp_path: Path,
) -> None:
    project: Path = prepare_semantic_corpus_project(
        base=semantic_playground, tmp_path=tmp_path, test_case=test_case
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project, command=("compile", "--no-cache", "--json")
    )
    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for code in test_case.expected_codes:
        assert code in result.stdout + result.stderr


@pytest.mark.xfail(strict=True, reason="Native coercion, signature, or structural coverage pending")
@pytest.mark.parametrize(
    "test_case",
    [SemanticCorpusCase(**case) for case in semantic_corpus_cases(group="pending")],
    ids=lambda case: case.description,
)
def test_given_pending_native_semantics_when_compiling_then_invalid_sql_should_error(
    test_case: SemanticCorpusCase,
    semantic_playground: Path,
    tmp_path: Path,
) -> None:
    project: Path = prepare_semantic_corpus_project(
        base=semantic_playground, tmp_path=tmp_path, test_case=test_case
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project, command=("compile", "--no-cache", "--json")
    )
    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [SemanticCorpusCase(**case) for case in semantic_corpus_cases(group="valid")],
    ids=lambda case: case.description,
)
def test_given_dialect_valid_control_when_compiling_and_building_then_both_succeed(
    test_case: SemanticCorpusCase,
    semantic_playground: Path,
    tmp_path: Path,
) -> None:
    project: Path = prepare_semantic_corpus_project(
        base=semantic_playground, tmp_path=tmp_path, test_case=test_case
    )
    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project, command=("compile", "--no-cache", "--json")
    )
    assert compiled.returncode == test_case.expected_exit_code, compiled.stdout + compiled.stderr
    built: subprocess.CompletedProcess[str] = run_sqb(project_dir=project, command=("build",))
    assert built.returncode == test_case.expected_exit_code, built.stdout + built.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
