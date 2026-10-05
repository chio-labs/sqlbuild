"""Sizing the render store for the load notice must tolerate files removed by a concurrent compile."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.compile_render_reuse._helpers import load_notice
from sqlbuild.cli.compile_reuse.constants import REUSE_RENDER_STATE_SUFFIX
from tests.unit.src.sqlbuild.cli.compile_render_reuse._helpers._test_types import (
    RenderLoadNoticeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderLoadNoticeTestCase(
            description="large_store_announced",
            file_sizes=(64, 64),
            removed_while_sizing=0,
            notice_bytes=100,
            expected_notice=True,
        ),
        RenderLoadNoticeTestCase(
            description="small_store_silent",
            file_sizes=(16, 16),
            removed_while_sizing=0,
            notice_bytes=100,
            expected_notice=False,
        ),
        RenderLoadNoticeTestCase(
            description="file_removed_while_sizing_counts_as_empty",
            file_sizes=(64, 64),
            removed_while_sizing=1,
            notice_bytes=100,
            expected_notice=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_render_files_when_starting_load_notice_then_sizes_without_failing(
    test_case: RenderLoadNoticeTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    entry_path: Path = tmp_path / "dev.entry"
    stored_paths: list[Path] = [
        tmp_path / f"dev-{index}{REUSE_RENDER_STATE_SUFFIX}"
        for index in range(len(test_case.file_sizes))
    ]
    for path, size in zip(stored_paths, test_case.file_sizes, strict=True):
        path.write_bytes(b"x" * size)
    listed: list[Path] = sorted(stored_paths)
    monkeypatch.setattr(load_notice, "RENDER_LOAD_NOTICE_BYTES", test_case.notice_bytes)
    monkeypatch.setattr(Path, "glob", lambda self, pattern: iter(listed))
    for path in listed[: test_case.removed_while_sizing]:
        path.unlink()

    # Act
    started: float | None = load_notice.start_load_notice(entry_path=entry_path)

    # Assert
    assert (started is not None) is test_case.expected_notice
    assert capsys.readouterr().out == ""
