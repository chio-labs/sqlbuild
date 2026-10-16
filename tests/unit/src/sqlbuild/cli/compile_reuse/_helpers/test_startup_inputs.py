import site
import sys
from pathlib import Path

import pytest

from sqlbuild.cli.compile_reuse._helpers.startup_inputs import startup_inputs
from tests.unit.src.sqlbuild.cli.compile_reuse._helpers._test_types import (
    StartupInputsErrorTestCase,
    StartupInputsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StartupInputsTestCase(
            description="relative, normalized and missing entries with their path files",
            folders=("a", "a-b", "a/b"),
            files=("a/q.pth", "a/notes.txt", "a-b/.pth"),
            path_entries=("a", "./a-b/", "a/b", "gone"),
            expected_stamps=(
                ("a", True),
                ("a/b", True),
                ("a/q.pth", True),
                ("a-b", True),
                ("a-b/.pth", True),
                ("gone", False),
                ("python", False),
                ("pyvenv.cfg", False),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_import_path_directories_when_stamping_then_lists_absolute_paths_and_pth_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: StartupInputsTestCase
) -> None:
    for folder in test_case.folders:
        (tmp_path / folder).mkdir(parents=True)
    for file in test_case.files:
        (tmp_path / file).write_text("x\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(test_case.path_entries))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setattr(sys, "prefix", str(tmp_path))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    monkeypatch.setattr(site, "getsitepackages", list)
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(tmp_path / "gone"))

    stamps: list[tuple[str, int | None, int | None]] = startup_inputs()
    listed: tuple[tuple[str, bool], ...] = tuple(
        (path.removeprefix(f"{tmp_path}/"), size is not None) for path, _, size in stamps
    )

    assert listed == test_case.expected_stamps
    assert stamps == sorted(stamps, key=lambda row: Path(row[0]))


@pytest.mark.parametrize(
    "test_case",
    [
        StartupInputsErrorTestCase(
            description="an entry below a regular file",
            files=("file.txt",),
            path_entry="file.txt/sub",
            expected_error=NotADirectoryError,
            expected_message=r"\[Errno 20\] Not a directory",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_import_path_entry_below_a_file_when_stamping_then_raises_the_stat_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: StartupInputsErrorTestCase
) -> None:
    for file in test_case.files:
        (tmp_path / file).write_text("x\n")
    monkeypatch.setattr(sys, "path", [str(tmp_path / test_case.path_entry)])

    with pytest.raises(test_case.expected_error, match=test_case.expected_message):
        startup_inputs()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
