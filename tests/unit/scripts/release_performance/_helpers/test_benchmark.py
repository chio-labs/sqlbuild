"""Unit tests for generating each version's release benchmark projects."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_performance._helpers.benchmark import write_baseline_pristine_projects
from scripts.release_performance._helpers.versions import release_source
from scripts.release_performance.exceptions import ReleasePerformanceError
from tests.unit.scripts.release_performance._helpers._test_types import (
    BaselineGeneratorTestCase,
    ReleaseSourceTestCase,
)
from tests.unit.scripts.release_performance._helpers.helpers import (
    FAILING_GENERATOR,
    MARKER_GENERATOR,
    tagged_repository,
    write_baseline_source,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BaselineGeneratorTestCase(
            description="the baseline source's own generator writes the baseline projects",
            generator=MARKER_GENERATOR,
            expected_projects=("build", "inspection"),
            expected_error_fragments=(),
        ),
        BaselineGeneratorTestCase(
            description="a failing baseline generator is reported with its stderr",
            generator=FAILING_GENERATOR,
            expected_projects=(),
            expected_error_fragments=(
                "Baseline benchmark generation with the generator in",
                "baseline generator exploded",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_baseline_source_when_generating_then_uses_its_own_generator(
    test_case: BaselineGeneratorTestCase, tmp_path: Path
) -> None:
    source: Path = write_baseline_source(root=tmp_path / "source", generator=test_case.generator)
    root: Path = tmp_path / "generated"
    error: str = ""

    try:
        _ = write_baseline_pristine_projects(
            source=source, root=root, inspection_models=30, build_models=10
        )
    except ReleasePerformanceError as raised:
        error = str(raised)

    pristine: Path = root / "pristine"
    assert tuple(sorted(path.parent.name for path in pristine.glob("*/BASELINE_MARKER"))) == (
        test_case.expected_projects
    )
    assert all(fragment in error for fragment in test_case.expected_error_fragments), error


@pytest.mark.parametrize(
    "test_case",
    [
        ReleaseSourceTestCase(
            description="the release tag's tree is extracted",
            tag="v1.2.3",
            requested_version="1.2.3",
            expected_files=("release.txt",),
            expected_error_fragments=(),
        ),
        ReleaseSourceTestCase(
            description="a missing release tag explains how to provide the source",
            tag="v1.2.3",
            requested_version="1.2.2",
            expected_files=(),
            expected_error_fragments=("Release tag v1.2.2 is not available", "--baseline-source"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_release_tag_when_extracting_source_then_returns_its_tree(
    test_case: ReleaseSourceTestCase, tmp_path: Path
) -> None:
    repository: Path = tagged_repository(root=tmp_path / "repo", tag=test_case.tag)
    destination: Path = tmp_path / "source"
    error: str = ""

    try:
        _ = release_source(
            version=test_case.requested_version, repo_dir=repository, destination=destination
        )
    except ReleasePerformanceError as raised:
        error = str(raised)

    assert tuple(sorted(path.name for path in destination.glob("*"))) == test_case.expected_files
    assert all(fragment in error for fragment in test_case.expected_error_fragments), error


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
