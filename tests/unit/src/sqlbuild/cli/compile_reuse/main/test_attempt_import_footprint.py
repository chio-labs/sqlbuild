"""A reused compile must not import the full compile pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_static_compile_project,
)
from tests.unit.src.sqlbuild.cli.compile_reuse.main._test_types import (
    ReuseImportFootprintTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_reuse.main.helpers import compile_in_fresh_process

_FULL_COMPILE_MODULES: tuple[str, ...] = (
    "sqlbuild.cli.commands.main.project._compile",
    "sqlbuild.cli.commands._helpers.compile.pipeline",
    "sqlbuild.compiler.pipeline.main.compiled_project",
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReuseImportFootprintTestCase(
            description="reuse_hit_skips_full_compile_modules",
            checked_modules=_FULL_COMPILE_MODULES,
            expected_full_loaded=_FULL_COMPILE_MODULES,
            expected_reused_loaded=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_compile_is_reused_then_full_compile_stays_unloaded(
    test_case: ReuseImportFootprintTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)

    full_code, full_loaded, _ = compile_in_fresh_process(
        project_dir=project_dir, checked_modules=test_case.checked_modules
    )
    reused_code, reused_loaded, reused_stderr = compile_in_fresh_process(
        project_dir=project_dir, checked_modules=test_case.checked_modules
    )

    assert (full_code, reused_code) == (0, 0)
    assert full_loaded == test_case.expected_full_loaded
    assert "Inputs unchanged; reused the previous compile" in reused_stderr
    assert reused_loaded == test_case.expected_reused_loaded


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
