"""Dense batched analysis preparation must match per-model preparation byte for byte."""

from pathlib import Path

import pytest

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from sqlbuild.compiler.compile.constants import COMPACT_RELATION_STUB_PREFIX
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    DenseBatchedPreparationTestCase,
    DensePreparedCompile,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    keep_batched_normalization,
    prepared_compile,
    use_per_model_normalization,
)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    (DenseBatchedPreparationTestCase("dense_models_3000", 3000, 0),),
    ids=lambda case: case.description,
)
def test_given_dense_project_when_compiling_cold_then_batched_preparation_matches_per_model(
    test_case: DenseBatchedPreparationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batched_dir: Path = tmp_path / "batched"
    reference_dir: Path = tmp_path / "reference"
    write_dense_compile_project(project_dir=batched_dir, model_count=test_case.model_count)
    write_dense_compile_project(project_dir=reference_dir, model_count=test_case.model_count)

    expected: DensePreparedCompile = prepared_compile(
        project_dir=reference_dir,
        args=(),
        capsys=capsys,
        monkeypatch=monkeypatch,
        normalization=use_per_model_normalization,
    )
    actual: DensePreparedCompile = prepared_compile(
        project_dir=batched_dir,
        args=(),
        capsys=capsys,
        monkeypatch=monkeypatch,
        normalization=keep_batched_normalization,
    )

    assert actual[3] == expected[3]
    assert actual[1] == expected[1]
    assert actual[2] == expected[2]
    assert actual[0] == expected[0]
    assert actual[0][0] == test_case.expected_exit_code
    assert any(COMPACT_RELATION_STUB_PREFIX.encode() in payload for payload in actual[3])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
