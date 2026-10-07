"""A real compile captures every discovered collection canonically, with callables as names."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.coverage.discovery import (
    discovered_input_kinds,
    discovery_capture_problems,
    discovery_collection_kinds,
)
from scripts.compiler_differential._helpers.running.execution import harness_environment
from scripts.compiler_differential.constants import (
    DISCOVERY_STAGE_CAPTURE_SUFFIX,
    GENERATOR_FEATURE_BLOCKS,
    SQB_ENTRY,
    STAGE_CAPTURE_ENV_VAR,
)
from scripts.compiler_differential.main.generate_project import generate_project
from tests.e2e.scripts.compiler_differential._test_types import DiscoveryCaptureTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoveryCaptureTestCase(
            description="every_feature_block",
            seed=11,
            blocks=GENERATOR_FEATURE_BLOCKS,
            expected_collections=frozenset(discovery_collection_kinds()),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_with_every_input_kind_when_capturing_discovery_then_capture_is_complete(
    test_case: DiscoveryCaptureTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    capture_dir: Path = tmp_path / "captures"
    generate_project(seed=test_case.seed, blocks=test_case.blocks).write(project_dir)

    _ = subprocess.run(
        [sys.executable, "-c", SQB_ENTRY, "--no-color", "compile", "--json"],
        cwd=project_dir,
        env={**harness_environment(), STAGE_CAPTURE_ENV_VAR: str(capture_dir)},
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )

    text: str = next(capture_dir.glob(f"*{DISCOVERY_STAGE_CAPTURE_SUFFIX}")).read_text(
        encoding="utf-8"
    )
    assert discovery_capture_problems(text) == ()
    assert test_case.expected_collections <= discovered_input_kinds(text)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
