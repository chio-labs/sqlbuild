"""Native-to-Python fallbacks are counted per site and kind and written once per process."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sqlbuild.compiler.frontier.classes.native_fallback_recorder import NativeFallbackRecorder
from sqlbuild.compiler.frontier.constants import NATIVE_FALLBACK_RECORD_PREFIX
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from tests.unit.src.sqlbuild.compiler.frontier._test_types import NativeFallbackRecorderTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFallbackRecorderTestCase(
            description="counts_per_site_and_kind_sorted",
            recorded=(
                (NativeFallbackSite.PROJECT_ASSEMBLY, "deferred"),
                (NativeFallbackSite.MACRO_CALL_MOCKED, "deferred"),
                (NativeFallbackSite.PROJECT_ASSEMBLY, "deferred"),
                (NativeFallbackSite.PROJECT_ASSEMBLY, "error"),
            ),
            expected_files=[
                [
                    ["macro_calls.mocked_evaluation", "deferred", 1],
                    ["project_assembly.assembly", "deferred", 2],
                    ["project_assembly.assembly", "error", 1],
                ]
            ],
        ),
        NativeFallbackRecorderTestCase(
            description="no_fallback_writes_no_file",
            recorded=(),
            expected_files=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_fallbacks_when_writing_then_one_file_holds_their_counts(
    test_case: NativeFallbackRecorderTestCase, tmp_path: Path
) -> None:
    recorder: NativeFallbackRecorder = NativeFallbackRecorder(directory=tmp_path / "records")
    for site, kind in test_case.recorded:
        recorder.record(site=site.value, kind=kind)

    recorder.write()

    written: list[list[list[object]]] = [
        json.loads(path.read_text(encoding="utf-8"))["fallbacks"]
        for path in sorted((tmp_path / "records").glob(f"{NATIVE_FALLBACK_RECORD_PREFIX}*"))
    ]
    assert [path.name for path in (tmp_path / "records").glob("*")] == [
        f"{NATIVE_FALLBACK_RECORD_PREFIX}{os.getpid()}.json"
    ] * len(test_case.expected_files)
    assert written == test_case.expected_files


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
