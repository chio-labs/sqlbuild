"""Native work counters for refactor command integration tests."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from sqlbuild.compiler.frontier._helpers.process_recorder import process_recorder
from sqlbuild.compiler.frontier.classes.native_fallback_recorder import NativeFallbackRecorder
from sqlbuild.compiler.frontier.constants import NATIVE_ANSWER_SITE_SUFFIX
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR

_REFACTORING_ANSWERS: str = f"{NativeStage.REFACTORING.value}{NATIVE_ANSWER_SITE_SUFFIX}"
_ANSWER_KINDS: tuple[str, ...] = ("planned_edits", "migration_edits")


def start_recording(*, record_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Record native answers of this process below `record_dir` until `refactoring_answers`."""

    monkeypatch.setenv(ANALYSIS_RECORD_DIR_ENV_VAR, str(record_dir))
    process_recorder.cache_clear()


def refactoring_answers(*, record_dir: Path) -> dict[str, int]:
    """Write the recorded counts and return the refactoring stage's native answer counts by kind."""

    recorder: NativeFallbackRecorder | None = process_recorder()
    assert recorder is not None
    recorder.write()
    process_recorder.cache_clear()
    counts: Counter[tuple[str, str]] = Counter()
    for path in sorted(record_dir.glob("native-fallbacks-*.json")):
        counts.update(
            {
                (str(site), str(kind)): int(count)
                for site, kind, count in json.loads(path.read_text(encoding="utf-8"))["fallbacks"]
            }
        )
    return {kind: counts[(_REFACTORING_ANSWERS, kind)] for kind in _ANSWER_KINDS}
