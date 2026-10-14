"""Harness arguments and baseline edits for the planner differential tests."""

from __future__ import annotations

import json
from pathlib import Path


def harness_arguments(
    *, mode: str, baseline_dir: Path, project: str, steps: tuple[str, ...]
) -> list[str]:
    """Return arguments running one corpus project through some steps of the script."""

    return [
        mode,
        "--baseline-dir",
        str(baseline_dir),
        "--projects",
        project,
        "--seeds",
        "0",
        "--jobs",
        "1",
        "--steps",
        *steps,
    ]


def baseline_steps(path: Path) -> list[dict[str, object]]:
    """Return a recorded project's step records."""

    steps: object = json.loads(path.read_text(encoding="utf-8"))["steps"]
    assert isinstance(steps, list)
    return steps


def tamper_plan_exit_code(*, path: Path, step_index: int) -> None:
    """Change one step's recorded `sqb plan --json` exit code, as a planner change would."""

    document: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    records: object = document["steps"]
    assert isinstance(records, list)
    records[step_index]["plan_json"]["exit_code"] = 7
    _ = path.write_text(json.dumps(document), encoding="utf-8")
