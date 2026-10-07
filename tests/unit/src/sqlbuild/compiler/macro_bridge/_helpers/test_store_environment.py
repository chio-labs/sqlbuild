from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.macro_bridge._helpers.store_environment import (
    module_stamps_metadata,
    store_environment,
    unchanged_module_stamps,
)
from tests.unit.src.sqlbuild.compiler.macro_bridge._helpers._test_types import (
    ModuleStampsRoundTripTestCase,
    ModuleStampsTestCase,
    StoreEnvironmentTestCase,
    StoreEnvironmentVariableTestCase,
)
from tests.unit.src.sqlbuild.compiler.macro_bridge._helpers.helpers import (
    EXCLUDED_MODEL_PATHS,
    removed_module,
    rewritten_module,
    write_environment_project,
    write_module,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModuleStampsTestCase(
            description="unchanged module",
            change=lambda path: write_module(path, "VALUE = 1\n"),
            expected_valid=True,
        ),
        ModuleStampsTestCase(
            description="module rewritten with the same size",
            change=rewritten_module,
            expected_valid=False,
        ),
        ModuleStampsTestCase(
            description="module removed", change=removed_module, expected_valid=False
        ),
        ModuleStampsTestCase(
            description="unreadable metadata", change=lambda _path: b"{", expected_valid=False
        ),
        ModuleStampsTestCase(
            description="unexpected metadata shape",
            change=lambda _path: b'[["flavor.py", "mtime", 1]]',
            expected_valid=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_module_stamps_when_validating_then_only_unchanged_modules_pass(
    tmp_path: Path, test_case: ModuleStampsTestCase
) -> None:
    metadata: bytes = test_case.change(tmp_path / "flavor.py")

    stamps: dict[str, tuple[int, int]] | None = unchanged_module_stamps(metadata)

    assert (stamps is not None) is test_case.expected_valid


@pytest.mark.parametrize(
    "test_case",
    [
        ModuleStampsRoundTripTestCase(
            description="one module", module_text="VALUE = 1\n", expected_valid=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_module_stamps_when_encoding_then_validation_returns_them(
    tmp_path: Path, test_case: ModuleStampsRoundTripTestCase
) -> None:
    path: Path = tmp_path / "flavor.py"
    _ = write_module(path, test_case.module_text)
    stamps: dict[str, tuple[int, int]] = {str(path): (path.stat().st_mtime_ns, path.stat().st_size)}

    validated: dict[str, tuple[int, int]] | None = unchanged_module_stamps(
        module_stamps_metadata(stamps)
    )

    assert (validated == stamps) is test_case.expected_valid


@pytest.mark.parametrize(
    "test_case",
    [
        StoreEnvironmentTestCase(
            description="no edit", edit=lambda _root: None, expected_unchanged=True
        ),
        StoreEnvironmentTestCase(
            description="model edit",
            edit=lambda root: (root / "models/orders.sql").write_text("SELECT 2\n"),
            expected_unchanged=True,
        ),
        StoreEnvironmentTestCase(
            description="macro edit",
            edit=lambda root: (root / "macros/common.py").write_text("X = 2\n"),
            expected_unchanged=False,
        ),
        StoreEnvironmentTestCase(
            description="model the caller does not exclude",
            edit=lambda root: (root / "models/customers.sql").write_text("SELECT 1\n"),
            expected_unchanged=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_edit_when_digesting_store_environment_then_only_model_edits_keep_it(
    tmp_path: Path, test_case: StoreEnvironmentTestCase
) -> None:
    write_environment_project(tmp_path)
    original: str = store_environment(project_dir=tmp_path, model_paths=EXCLUDED_MODEL_PATHS)
    _ = test_case.edit(tmp_path)

    edited: str = store_environment(project_dir=tmp_path, model_paths=EXCLUDED_MODEL_PATHS)

    assert (edited == original) is test_case.expected_unchanged


@pytest.mark.parametrize(
    "test_case",
    [
        StoreEnvironmentVariableTestCase(
            description="variable a macro may read",
            name="SQB_STORE_REGION",
            value="south",
            expected_unchanged=False,
        ),
        StoreEnvironmentVariableTestCase(
            description="compiler engine selection",
            name="SQLBUILD_COMPILER_ENGINE",
            value="python",
            expected_unchanged=True,
        ),
        StoreEnvironmentVariableTestCase(
            description="variable outside the tracked prefixes",
            name="STORE_REGION",
            value="south",
            expected_unchanged=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_environment_variable_change_when_digesting_store_environment_then_tracked_ones_count(
    tmp_path: Path, test_case: StoreEnvironmentVariableTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_environment_project(tmp_path)
    monkeypatch.delenv(test_case.name, raising=False)
    original: str = store_environment(project_dir=tmp_path, model_paths=EXCLUDED_MODEL_PATHS)
    monkeypatch.setenv(test_case.name, test_case.value)

    changed: str = store_environment(project_dir=tmp_path, model_paths=EXCLUDED_MODEL_PATHS)

    assert (changed == original) is test_case.expected_unchanged
