"""Exercise candidate installation with an unpublished companion wheel."""

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.release_performance._helpers.versions import install_wheel, installed_version


@pytest.mark.skipif(sys.platform == "win32", reason="Release comparison uses POSIX environments")
def test_given_unpublished_companion_when_installing_candidate_then_resolves_local_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("UV_NO_INDEX", "1")
    wheels: Path = tmp_path / "wheels"
    wheels.mkdir()
    for name in ("sqlbuild", "sqlbuild_cli"):
        metadata: str = f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n"
        if name == "sqlbuild":
            metadata += "Requires-Dist: sqlbuild-cli==0.1.0\n"
        with ZipFile(wheels / f"{name}-0.1.0-py3-none-any.whl", "w") as wheel:
            info: str = f"{name}-0.1.0.dist-info"
            wheel.writestr(f"{info}/METADATA", metadata)
            wheel.writestr(
                f"{info}/WHEEL",
                "Wheel-Version: 1.0\nGenerator: release-probe\n"
                "Root-Is-Purelib: true\nTag: py3-none-any\n",
            )
            wheel.writestr(f"{info}/RECORD", "")
            if name == "sqlbuild_cli":
                wheel.writestr("release_probe.py", "def main():\n    print('sqlbuild 0.1.0')\n")
                wheel.writestr(
                    f"{info}/entry_points.txt", "[console_scripts]\nsqb = release_probe:main\n"
                )
    sqb: Path = install_wheel(
        wheel=wheels / "sqlbuild-0.1.0-py3-none-any.whl",
        venv_dir=tmp_path / "candidate",
        python=sys.executable,
    )
    assert installed_version(sqb=sqb) == "0.1.0"
