"""Both compiler engines produce identical compiles and never share on-disk compile stores."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompilerEngineMacroParityTestCase,
    CompilerEngineParityTestCase,
    CompilerEngineRulesStoreTestCase,
    CompilerEngineStoreTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    engine_compile_and_rules,
    engine_reuse_compile,
    environment_engine_reuse_compile,
    prepare_compile_reuse_project,
    report_engine,
    report_without_engine,
    store_digests,
)
from tests.integration.src.sqlbuild.compiler.compile.helpers import (
    MACRO_BRIDGE_PROJECT_FILES,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineParityTestCase(
            description="python_and_native",
            left_engine="python",
            right_engine="native",
            expected_engines=("python", "native"),
            expected_exit_codes=(0, 0),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_project_when_compiling_with_each_engine_then_outputs_are_identical(
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
        CompilerEngineParityTestCase(
            description="python_oracle_and_unset_default",
            left_engine="python",
            right_engine="",
            expected_engines=("python", "native"),
            expected_exit_codes=(0, 0),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_engine_selection_when_compiling_then_native_runs_and_matches_python(
    test_case: CompilerEngineParityTestCase, tmp_path: Path
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    oracle: CompileReuseRun = environment_engine_reuse_compile(
        project_dir=copy_compile_project(source=prepared_project, destination=tmp_path / "oracle"),
        engine=test_case.left_engine,
    )
    default: CompileReuseRun = environment_engine_reuse_compile(
        project_dir=copy_compile_project(source=prepared_project, destination=tmp_path / "default"),
        engine=test_case.right_engine,
    )

    assert (oracle.returncode, default.returncode) == test_case.expected_exit_codes
    assert (report_engine(oracle), report_engine(default)) == test_case.expected_engines
    assert report_without_engine(default) == report_without_engine(oracle)
    assert default.compiled == oracle.compiled
    assert oracle.compiled


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineMacroParityTestCase(
            description="macros_in_models_hooks_tests_audits_sources_functions",
            files={
                path: content.replace("WHERE id IN @generated_join()\n", "")
                for path, content in MACRO_BRIDGE_PROJECT_FILES.items()
            },
            expected_exit_codes=(0, 0),
            expected_compiled_fragments=("amount * 21", "'__SQLBUILD_RELATION_1__'"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_macro_heavy_project_when_compiling_with_each_engine_then_outputs_are_identical(
    test_case: CompilerEngineMacroParityTestCase, tmp_path: Path
) -> None:
    python_run: CompileReuseRun = engine_reuse_compile(
        project_dir=write_project(root=tmp_path / "python", files=test_case.files),
        engine="python",
    )
    native_run: CompileReuseRun = engine_reuse_compile(
        project_dir=write_project(root=tmp_path / "native", files=test_case.files),
        engine="native-preview",
    )
    compiled_text: str = b"".join(python_run.compiled.values()).decode()

    assert (python_run.returncode, native_run.returncode) == test_case.expected_exit_codes
    assert report_without_engine(native_run) == report_without_engine(python_run)
    assert native_run.compiled == python_run.compiled
    assert all(map(compiled_text.__contains__, test_case.expected_compiled_fragments))


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineStoreTestCase(
            description="python_native_native_python",
            engines=("python", "native", "native", "python"),
            expected_reused=(False, False, True, True),
            expected_python_stores=("target/cache/compiler", "target/rules-cache"),
            expected_native_stores=(
                "target/cache/compiler-native-v1",
                "target/rules-cache-native-v1",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compile_by_one_engine_when_other_engine_compiles_then_no_store_is_shared(
    test_case: CompilerEngineStoreTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=project_dir)

    first: CompileReuseRun = engine_reuse_compile(
        project_dir=project_dir, engine=test_case.engines[0]
    )
    python_stores: dict[str, str] = store_digests(
        project_dir=project_dir, stores=test_case.expected_python_stores
    )
    later: list[CompileReuseRun] = [
        engine_reuse_compile(project_dir=project_dir, engine=engine)
        for engine in test_case.engines[1:-1]
    ]
    python_stores_after_native: dict[str, str] = store_digests(
        project_dir=project_dir, stores=test_case.expected_python_stores
    )
    last: CompileReuseRun = engine_reuse_compile(
        project_dir=project_dir, engine=test_case.engines[-1]
    )
    runs: list[CompileReuseRun] = [first, *later, last]

    assert tuple(run.reused for run in runs) == test_case.expected_reused
    assert python_stores
    assert python_stores_after_native == python_stores
    assert store_digests(project_dir=project_dir, stores=test_case.expected_native_stores)
    assert {report_without_engine(run) for run in runs[2:]} == {report_without_engine(last)}


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineRulesStoreTestCase(
            description="built_in_rules_after_compile",
            rules_selector="SQBR",
            stores=("target/cache", "target/rules-cache", "target/rules-cache-native-v1"),
            native_marker="-native-v1/",
            expected_python_files=(
                "target/rules-cache/bulk/native.json",
                "target/rules-cache/bulk/sql.json",
            ),
            expected_native_files=(
                "target/rules-cache-native-v1/bulk/native.json",
                "target/rules-cache-native-v1/bulk/sql.json",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_compile_and_rules_when_native_runs_them_then_native_writes_only_its_stores(
    test_case: CompilerEngineRulesStoreTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=project_dir)

    python_exit: int = engine_compile_and_rules(
        project_dir=project_dir, engine="python", rules_selector=test_case.rules_selector
    )
    python_files: dict[str, str] = store_digests(project_dir=project_dir, stores=test_case.stores)
    native_exit: int = engine_compile_and_rules(
        project_dir=project_dir, engine="native", rules_selector=test_case.rules_selector
    )
    all_files: dict[str, str] = store_digests(project_dir=project_dir, stores=test_case.stores)
    native_files: set[str] = set(all_files) - set(python_files)

    assert native_exit == python_exit
    assert {path: all_files.get(path) for path in python_files} == python_files
    assert all(test_case.native_marker in path for path in native_files), sorted(native_files)
    assert set(test_case.expected_python_files) <= set(python_files)
    assert set(test_case.expected_native_files) <= native_files


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
