"""Run the build feature alignment check with Cargo over real workspaces."""

import shutil
from pathlib import Path

import pytest

from scripts.build_features.main.check import run_build_features_check
from tests.integration.scripts.build_features._test_types import (
    BuildFeaturesTestCase,
    RepositoryBuildFeaturesTestCase,
)
from tests.integration.scripts.build_features.helpers import write_workspace

pytestmark: pytest.MarkDecorator = pytest.mark.skipif(
    shutil.which("cargo") is None, reason="Cargo is not installed"
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildFeaturesTestCase(
            description="both builds resolve the shared crates identically",
            extension_shared_features=(),
            extension_host_features=(),
            expected_exit_code=0,
            expected_drift=(),
        ),
        BuildFeaturesTestCase(
            description="the extension enables a feature of a shared target crate",
            extension_shared_features=("extra",),
            extension_host_features=(),
            expected_exit_code=1,
            expected_drift=(
                "x86_64-unknown-linux-gnu target shared v0.1.0: sqb (none), extension extra",
            ),
        ),
        BuildFeaturesTestCase(
            description="the extension enables a feature of a crate a shared proc-macro uses",
            extension_shared_features=(),
            extension_host_features=("more",),
            expected_exit_code=1,
            expected_drift=(
                "x86_64-unknown-linux-gnu host helper v0.1.0: sqb (none), extension more",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_workspace_when_checking_build_features_then_reports_crates_compiled_twice(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_case: BuildFeaturesTestCase,
) -> None:
    write_workspace(tmp_path, test_case)
    monkeypatch.setenv("CARGO_TERM_COLOR", "always")

    exit_code: int = run_build_features_check(["--root", str(tmp_path)])

    errors: str = capsys.readouterr().err
    assert exit_code == test_case.expected_exit_code
    for drift in test_case.expected_drift:
        assert f"- {drift}" in errors


@pytest.mark.parametrize(
    "test_case",
    [
        RepositoryBuildFeaturesTestCase(
            description="the repository sqb and extension builds share every common crate",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repository_when_checking_build_features_then_builds_share_crates(
    test_case: RepositoryBuildFeaturesTestCase,
) -> None:
    repository: Path = Path(__file__).resolve().parents[4]

    assert run_build_features_check(["--root", str(repository)]) == test_case.expected_exit_code
