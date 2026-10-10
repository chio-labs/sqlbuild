"""Expected outputs recorded once from the pre-port Python implementations, compared by digest.

Each golden file holds the Python oracle's view of every seam call a test makes, in call order,
as `[kind, digest]` or `[kind, {name: digest}]` entries. A test rebuilds the same entries from
the native result and must match them exactly, so two equal native runs cannot stand in for
the deleted Python oracle.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import cast

GOLDEN_DIR: Path = Path(__file__).resolve().parents[4] / "goldens" / "python_oracle"

type GoldenEntry = list[object]


def canonical(value: object) -> object:
    """A JSON value standing for `value`, equal exactly when the Python values are equal."""

    if isinstance(value, Enum):
        return [type(value).__name__, canonical(value.value)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            type(value).__name__,
            {
                field.name: canonical(getattr(value, field.name))
                for field in dataclasses.fields(value)
            },
        ]
    if isinstance(value, dict):
        return [
            ["key", canonical(key), canonical(item)]
            for key, item in sorted(
                value.items(), key=lambda pair: json.dumps(canonical(pair[0]), sort_keys=True)
            )
        ]
    if isinstance(value, list | tuple):
        return [type(value).__name__, [canonical(item) for item in value]]
    if isinstance(value, frozenset | set):
        return ["set", sorted((canonical(item) for item in value), key=json.dumps)]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return ["repr", repr(value)]


def digest(value: object) -> str:
    """The SHA-256 of `value`'s canonical JSON, shortened for golden files."""

    encoded: bytes = json.dumps(canonical(value), sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def golden_entry(kind: str, view: object) -> GoldenEntry:
    """One seam call's golden entry: a digest per named item for mappings, else one digest."""

    if isinstance(view, dict):
        return [kind, {str(name): digest(item) for name, item in view.items()}]
    return [kind, digest(view)]


def golden_name(prefix: str, description: str) -> str:
    """The golden file name of a test case: its prefix and its description as a slug."""

    return f"{prefix}_{re.sub(r'[^a-z0-9]+', '_', description.lower()).strip('_')}"


def read_golden(name: str) -> list[GoldenEntry]:
    """The recorded entries of one golden file."""

    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


def write_golden(name: str, entries: list[GoldenEntry]) -> None:
    """Record one golden file; used only by the one-off oracle recording."""

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    _ = (GOLDEN_DIR / f"{name}.json").write_text(
        json.dumps(entries, indent=0, sort_keys=True) + "\n", encoding="utf-8"
    )


def golden_differences(
    expected: list[GoldenEntry], actual: list[GoldenEntry]
) -> list[tuple[int, str, object, object]]:
    """`(index, kind, expected, actual)` for every entry that differs, names compared one by one."""

    differences: list[tuple[int, str, object, object]] = []
    for index in range(max(len(expected), len(actual))):
        want: GoldenEntry | None = expected[index] if index < len(expected) else None
        got: GoldenEntry | None = actual[index] if index < len(actual) else None
        if want == got:
            continue
        want_items: object = want[1] if want is not None else None
        got_items: object = got[1] if got is not None else None
        if (
            want is not None
            and got is not None
            and want[0] == got[0]
            and isinstance(want_items, dict)
            and isinstance(got_items, dict)
        ):
            want_digests: dict[str, object] = cast(dict[str, object], want_items)
            got_digests: dict[str, object] = cast(dict[str, object], got_items)
            differences.extend(
                (index, f"{want[0]}:{name}", want_digests.get(name), got_digests.get(name))
                for name in sorted({*want_digests, *got_digests})
                if want_digests.get(name) != got_digests.get(name)
            )
            continue
        differences.append(
            (index, str((want or got or ["?"])[0]), want and want[1], got and got[1])
        )
    return differences
