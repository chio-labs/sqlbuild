"""Write a run as the baseline, or compare it with the recorded baseline."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.planner_differential.constants import BASELINE_SUFFIX, MAX_DIFF_LINES
from scripts.planner_differential.models import ProjectDifference

_STEP_KEY: str = "step"
_STEPS_KEY: str = "steps"
_MISSING: str = "<missing>"
_TYPE_MARKERS: frozenset[str] = frozenset({"__type__", "__enum__"})


def write_document(*, directory: Path, slug: str, document: dict[str, object]) -> Path:
    """Write one project's run as stable, indented JSON."""

    directory.mkdir(parents=True, exist_ok=True)
    path: Path = directory / f"{slug}{BASELINE_SUFFIX}"
    _ = path.write_text(_rendered(document) + "\n", encoding="utf-8", newline="\n")
    return path


def read_document(*, directory: Path, slug: str) -> dict[str, object] | None:
    """Return a recorded project run, or None when the baseline has none."""

    path: Path = directory / f"{slug}{BASELINE_SUFFIX}"
    if not path.is_file():
        return None
    return as_json_object(json.loads(path.read_text(encoding="utf-8")))


def compare_documents(
    *, expected: dict[str, object], actual: dict[str, object]
) -> tuple[ProjectDifference, ...]:
    """Return a readable diff for every step artifact that differs from the baseline."""

    expected_steps: list[dict[str, object]] = _steps(expected)
    actual_steps: list[dict[str, object]] = _steps(actual)
    differences: list[ProjectDifference] = []
    for index in range(max(len(expected_steps), len(actual_steps))):
        left: dict[str, object] = expected_steps[index] if index < len(expected_steps) else {}
        right: dict[str, object] = actual_steps[index] if index < len(actual_steps) else {}
        step: str = str(right.get(_STEP_KEY, left.get(_STEP_KEY, index)))
        left = _without_type_modules(left)
        right = _without_type_modules(right)
        for artifact in (*left, *(key for key in right if key not in left)):
            if left.get(artifact, _MISSING) == right.get(artifact, _MISSING):
                continue
            differences.append(
                ProjectDifference(
                    step=step,
                    artifact=artifact,
                    diff=unified_diff(
                        expected=left.get(artifact, _MISSING),
                        actual=right.get(artifact, _MISSING),
                    ),
                )
            )
    return tuple(differences)


def unified_diff(*, expected: object, actual: object) -> str:
    """Return a bounded unified diff of two JSON values rendered one item per line."""

    lines: list[str] = list(
        difflib.unified_diff(
            _rendered(expected).splitlines(),
            _rendered(actual).splitlines(),
            fromfile="baseline",
            tofile="actual",
            lineterm="",
            n=2,
        )
    )
    if len(lines) > MAX_DIFF_LINES:
        omitted: int = len(lines) - MAX_DIFF_LINES
        lines = [*lines[:MAX_DIFF_LINES], f"... {omitted} more diff lines"]
    return "\n".join(lines)


def _steps(document: dict[str, object]) -> list[dict[str, object]]:
    steps: object = document.get(_STEPS_KEY)
    if not isinstance(steps, list):
        return []
    return [mapping for step in steps if (mapping := as_json_object(step)) is not None]


def _without_type_modules(value: dict[str, object]) -> dict[str, object]:
    """Compare captured class and enum names without their module, which moves when a type is
    hosted natively."""

    return {key: _type_names_only(key=key, value=item) for key, item in value.items()}


def _type_names_only(*, key: str, value: object) -> object:
    if key in _TYPE_MARKERS and isinstance(value, str):
        return value.rpartition(":")[2]
    if isinstance(value, dict):
        return {
            str(inner_key): _type_names_only(key=str(inner_key), value=item)
            for inner_key, item in value.items()
        }
    if isinstance(value, list):
        return [_type_names_only(key="", value=item) for item in value]
    return value


def _rendered(value: object) -> str:
    return json.dumps(value, indent=1, ensure_ascii=False)
