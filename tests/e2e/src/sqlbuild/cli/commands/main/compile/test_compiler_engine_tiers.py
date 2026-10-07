"""The native-preview tier matches Python and never shares stores with the shipped native tier."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompilerEngineParityTestCase,
    CompilerEngineTierStoreTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    engine_reuse_compile,
    prepare_compile_reuse_project,
    report_engine,
    report_without_engine,
    store_digests,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineParityTestCase(
            description="python_and_native_preview",
            left_engine="python",
            right_engine="native-preview",
            expected_engines=("python", "native-preview"),
            expected_exit_codes=(0, 0),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_project_when_compiling_with_preview_tier_then_outputs_match_python(
    test_case: CompilerEngineParityTestCase, tmp_path: Path
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    left: CompileReuseRun = engine_reuse_compile(
        project_dir=copy_compile_project(source=prepared_project, destination=tmp_path / "left"),
        engine=test_case.left_engine,
    )
    right: CompileReuseRun = engine_reuse_compile(
        project_dir=copy_compile_project(source=prepared_project, destination=tmp_path / "right"),
        engine=test_case.right_engine,
    )

    assert (left.returncode, right.returncode) == test_case.expected_exit_codes
    assert (report_engine(left), report_engine(right)) == test_case.expected_engines
    assert report_without_engine(right) == report_without_engine(left)
    assert right.compiled == left.compiled
    assert left.compiled


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineTierStoreTestCase(
            description="native_preview_preview_native",
            engines=("native", "native-preview", "native-preview", "native"),
            expected_reused=(False, False, True, True),
            expected_first_engine_stores=(
                "target/cache/compiler-native-v1",
                "target/rules-cache-native-v1",
            ),
            expected_second_engine_stores=(
                "target/cache/compiler-native-preview-v1",
                "target/rules-cache-native-preview-v1",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shipped_native_compile_when_preview_compiles_then_no_store_is_shared(
    test_case: CompilerEngineTierStoreTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=project_dir)

    first: CompileReuseRun = engine_reuse_compile(
        project_dir=project_dir, engine=test_case.engines[0]
    )
    first_stores: dict[str, str] = store_digests(
        project_dir=project_dir, stores=test_case.expected_first_engine_stores
    )
    later: list[CompileReuseRun] = [
        engine_reuse_compile(project_dir=project_dir, engine=engine)
        for engine in test_case.engines[1:-1]
    ]
    first_stores_after_preview: dict[str, str] = store_digests(
        project_dir=project_dir, stores=test_case.expected_first_engine_stores
    )
    last: CompileReuseRun = engine_reuse_compile(
        project_dir=project_dir, engine=test_case.engines[-1]
    )
    runs: list[CompileReuseRun] = [first, *later, last]

    assert tuple(run.reused for run in runs) == test_case.expected_reused
    assert first_stores
    assert first_stores_after_preview == first_stores
    assert store_digests(project_dir=project_dir, stores=test_case.expected_second_engine_stores)
    assert {report_without_engine(run) for run in runs[2:]} == {report_without_engine(last)}


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
