from pathlib import Path

import pytest

from scripts.native_layering._helpers.versions import get_native_version_errors
from tests.unit.scripts.native_layering._helpers._test_types import (
    NativeVersionTestCase,
    RepositoryLayeringTestCase,
)
from tests.unit.scripts.native_layering._helpers.helpers import write_versions


@pytest.mark.parametrize(
    "test_case",
    [
        NativeVersionTestCase(
            description="every release version source agrees",
            workspace_version="1.2.0",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.2.0",
            expected_errors=(),
            lock_versions={"example-core": "1.2.0", "example-cli": "1.2.0"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_matching_versions_when_checking_then_returns_no_errors(
    tmp_path: Path, test_case: NativeVersionTestCase
) -> None:
    write_versions(tmp_path, test_case)

    assert get_native_version_errors(tmp_path) == test_case.expected_errors


@pytest.mark.parametrize(
    "test_case",
    [
        NativeVersionTestCase(
            description="workspace version lags a release",
            workspace_version="1.1.9",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.2.0",
            expected_errors=(
                "Release versions differ: Cargo.toml [workspace.package] version is 1.1.9, "
                "pyproject.toml [project] version is 1.2.0, "
                ".release-please-manifest.json version is 1.2.0, "
                "pyproject.toml sqlbuild-cli dependency is 1.2.0.",
            ),
        ),
        NativeVersionTestCase(
            description="native executable pin lags a release",
            workspace_version="1.2.0",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.1.9",
            expected_errors=(
                "Release versions differ: Cargo.toml [workspace.package] version is 1.2.0, "
                "pyproject.toml [project] version is 1.2.0, "
                ".release-please-manifest.json version is 1.2.0, "
                "pyproject.toml sqlbuild-cli dependency is 1.1.9.",
            ),
        ),
        NativeVersionTestCase(
            description="lockfile kept the previous workspace version after a release bump",
            workspace_version="1.2.0",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.2.0",
            lock_versions={"example-core": "1.1.9", "example-cli": "1.1.9"},
            expected_errors=(
                "Cargo.lock workspace crate versions are stale: example-cli is 1.1.9, not 1.2.0; "
                "example-core is 1.1.9, not 1.2.0. Run `cargo update --workspace`.",
            ),
        ),
        NativeVersionTestCase(
            description="uv lockfile kept the previous project version after a release bump",
            workspace_version="1.2.0",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.2.0",
            lock_versions={"example-cli": "1.2.0"},
            python_lock_version="1.1.9",
            expected_errors=(
                "uv.lock locks example at 1.1.9, not pyproject.toml 1.2.0. Run `uv lock`.",
            ),
        ),
        NativeVersionTestCase(
            description="one workspace crate lags in the lockfile",
            workspace_version="1.2.0",
            pyproject_version="1.2.0",
            release_version="1.2.0",
            cli_version="1.2.0",
            lock_versions={"example-core": "1.2.0", "example-cli": "1.1.9"},
            expected_errors=(
                "Cargo.lock workspace crate versions are stale: example-cli is 1.1.9, not 1.2.0. "
                "Run `cargo update --workspace`.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_diverged_versions_when_checking_then_reports_them(
    tmp_path: Path, test_case: NativeVersionTestCase
) -> None:
    write_versions(tmp_path, test_case)

    assert get_native_version_errors(tmp_path) == test_case.expected_errors


@pytest.mark.parametrize(
    "test_case",
    [
        RepositoryLayeringTestCase(
            description="repository release versions agree",
            expected_errors=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_when_checking_versions_then_they_agree(
    test_case: RepositoryLayeringTestCase,
) -> None:
    repository: Path = Path(__file__).resolve().parents[5]

    assert get_native_version_errors(repository) == test_case.expected_errors


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
