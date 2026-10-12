"""Exercise candidate installation with an unpublished companion wheel."""

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.release_performance._helpers.versions import install_wheel, installed_version
from tests.integration.scripts.release_performance._test_types import LocalWheelTestCase


@pytest.mark.skipif(sys.platform == "win32", reason="Release comparison uses POSIX environments")
@pytest.mark.parametrize("test_case", [LocalWheelTestCase(version="0.1.0")])
def test_given_unpublished_companion_when_installing_candidate_then_resolves_local_wheel(
    test_case: LocalWheelTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_NO_INDEX", "1")
    wheels: Path = tmp_path / "wheels"
    wheels.mkdir()
    version: str = test_case.version
    for name, dependency, entry_points in (
        ("sqlbuild", f"Requires-Dist: sqlbuild-cli=={version}\n", ""),
        ("sqlbuild_cli", "", "[console_scripts]\nsqb = sqlbuild_cli_probe:main\n"),
    ):
        metadata: str = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n{dependency}"
        with ZipFile(wheels / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
            info: str = f"{name}-{version}.dist-info"
            wheel.writestr(f"{info}/METADATA", metadata)
            wheel.writestr(
                f"{info}/WHEEL",
                "Wheel-Version: 1.0\nGenerator: release-probe\n"
                "Root-Is-Purelib: true\nTag: py3-none-any\n",
            )
            wheel.writestr(f"{info}/RECORD", "")
            wheel.writestr(f"{name}_probe.py", f"def main():\n    print('sqlbuild {version}')\n")
            wheel.writestr(f"{info}/entry_points.txt", entry_points)
    sqb: Path = install_wheel(
        wheel=wheels / f"sqlbuild-{version}-py3-none-any.whl",
        venv_dir=tmp_path / "candidate",
        python=sys.executable,
    )
    assert installed_version(sqb=sqb) == version
