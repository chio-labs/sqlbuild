"""Seeded TOML generators and canonical values for the native configuration oracles."""

from __future__ import annotations

import datetime
import json
import math
import random
import struct
import tomllib
from collections.abc import Callable
from contextlib import suppress
from itertools import compress
from pathlib import Path
from typing import Any

from sqlbuild import _native
from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from tests.integration.src.sqlbuild.compiler.helpers import random_float, random_text

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[6]
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset({".venv", "node_modules", "target", ".git"})
PYTHON_ERROR: dict[str, str] = {"error": "rejected"}
DEFERRED: dict[str, str] = {"error": "deferred to Python"}
UNCHECKED_PYTHON_OUTCOMES: tuple[dict[str, str], ...] = (PYTHON_ERROR,)
YAML_LINE_BREAKS: dict[int, None] = {0x85: None, 0x2028: None, 0x2029: None}
BYTE_ORDER_MARKS: tuple[str, ...] = ("",) * 19 + ("\ufeff",)


def yaml_text(*, rng: random.Random, max_length: int) -> str:
    """Return random text without the line breaks only YAML 1.1 recognizes."""

    return random_text(rng=rng, max_length=max_length).translate(YAML_LINE_BREAKS)


HOSTILE_TOML_DOCUMENTS: dict[str, Callable[[], str]] = {
    "deep arrays": lambda: "a = " + "[" * 10_000 + "]" * 10_000,
    "deep inline tables": lambda: "a = " + "{b = " * 10_000 + "}" * 10_000,
    "long dotted key": lambda: "a" + ".a" * 100_000 + " = 1",
    "long table header": lambda: "[a" + ".a" * 100_000 + "]",
}


def _toml_key(rng: random.Random, index: int) -> str:
    bare: str = f"k{index}_{rng.choice(('a', 'B', '1', '-', '_'))}"
    quoted: str = json.dumps(yaml_text(rng=rng, max_length=5) + str(index), ensure_ascii=False)
    literal: str = f"'{rng.choice(('é', 'x y', 'dot.ted'))}{index}'"
    return rng.choice((bare, bare, quoted, literal))


def _toml_datetime(rng: random.Random) -> str:
    date: str = f"{rng.randint(1, 9999):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    time: str = f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
    fraction: str = rng.choice(("", f".{rng.randint(0, 10**9)}", ".5"))
    offset: str = rng.choice(
        ("", "Z", "z", f"{rng.choice('+-')}{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}")
    )
    return rng.choice(
        (date, f"{time}{fraction}", f"{date}T{time}{fraction}{offset}", f"{date} {time}{offset}")
    )


def _toml_float(rng: random.Random) -> str:
    value: float = random_float(rng=rng)
    exponent: str = f"{rng.randint(-99, 99)}.{rng.randint(0, 99)}e{rng.randint(-30, 30)}"
    return rng.choice((repr(value), exponent, "1_000.5", "-0.0", "+inf", "-nan"))


TOML_ESCAPES: tuple[str, ...] = (
    "\\b", "\\t", "\\n", "\\f", "\\r", '\\"', "\\\\", "\\u00e9", "\\U0001F600",
)  # fmt: skip
TOML_STRING_LITERALS: tuple[str, ...] = (
    "'C:\\path'",
    "'a \"q\"'",
    "'é'",
    '"""\nline"""',
    '"""\none\\\n   two"""',
    "'''\nraw \\n'''",
    "'''\ntwo\nlines'''",
)
TOML_1_1_SYNTAX: tuple[str, ...] = (
    '"\\e"',
    '"\\x41"',
    "{x = 1,}",
    "{\n  x = 1\n}",
    "{x = 1, # note\n}",
    "07:32",
    "1979-05-27T07:32Z",
    "1979-05-27 07:32",
)
TOML_TABLE_NAMES: tuple[str, ...] = ("p", "p.q", "p.q.r", "p.s", "t", "t.u", '"p".v')
TOML_SCALARS: tuple[Callable[[random.Random], str], ...] = (
    lambda rng: rng.choice((*TOML_1_1_SYNTAX, str(2**64), str(-(2**80)))),
    lambda rng: str(rng.randint(-(2**63), 2**63 - 1)),
    lambda rng: rng.choice(("0x1F", "0o17", "0b101", "1_000", "+7", "-0")),
    _toml_float,
    lambda rng: rng.choice(("true", "false")),
    lambda rng: json.dumps(yaml_text(rng=rng, max_length=10), ensure_ascii=False),
    lambda rng: '"' + "".join(rng.choice(TOML_ESCAPES) for _ in range(rng.randint(0, 3))) + 'x"',
    lambda rng: rng.choice(TOML_STRING_LITERALS),
    _toml_datetime,
)


def _toml_inline(rng: random.Random, depth: int) -> str:
    entries: str = ", ".join(
        f"{_toml_key(rng, index)} = {random_toml_value(rng=rng, depth=depth - 1)}"
        for index in range(rng.randint(0, 3))
    )
    return "{" + entries + "}"


def _toml_array(rng: random.Random, depth: int) -> str:
    values: list[str] = [
        random_toml_value(rng=rng, depth=depth - 1) for _ in range(rng.randint(0, 3))
    ]
    return "[" + rng.choice((", ", ",\n  ")).join(values) + rng.choice(("", ",")) + "]"


TOML_GENERATORS: tuple[Callable[[random.Random, int], str], ...] = (
    *(lambda rng, depth, scalar=scalar: scalar(rng) for scalar in TOML_SCALARS),
    _toml_inline,
    _toml_array,
)


def random_toml_value(*, rng: random.Random, depth: int) -> str:
    """Return the TOML text of a random value."""

    available: int = len(TOML_SCALARS) + 2 * min(depth, 1)
    return rng.choice(TOML_GENERATORS[:available])(rng, depth)


def _toml_pairs(rng: random.Random, prefix: str) -> str:
    return "".join(
        f"{prefix}{_toml_key(rng, index)} = {random_toml_value(rng=rng, depth=2)}"
        f"{rng.choice(('', '  # note'))}\n"
        for index in range(rng.randint(0, 4))
    )


def toml_document(*, rng: random.Random) -> str:
    """Return a TOML document with root keys, dotted keys, tables and arrays of tables.

    Table names repeat across sections, so implicit tables are later declared explicitly or
    extended through dotted keys, as `tomllib` orders them by first creation.
    """

    sections: list[str] = [
        rng.choice(
            (
                f"[table{index}]\n{_toml_pairs(rng, '')}",
                f"[parent.child{index}]\n{_toml_pairs(rng, '')}",
                f"[[rows]]\n{_toml_pairs(rng, '')}",
                f"{_toml_pairs(rng, f'dotted{index}.')}",
                f"[{rng.choice(TOML_TABLE_NAMES)}]\n{_toml_pairs(rng, '')}",
                f"[[{rng.choice(TOML_TABLE_NAMES)}]]\n{_toml_pairs(rng, '')}",
                f"{_toml_pairs(rng, rng.choice(TOML_TABLE_NAMES) + '.')}",
                f"[late{index}.inner]\n{_toml_pairs(rng, '')}[side{index}]\n"
                f"{_toml_pairs(rng, '')}[late{index}]\n{_toml_pairs(rng, '')}",
                f"[[late{index}.rows]]\n{_toml_pairs(rng, '')}[late{index}]\n"
                f"{_toml_pairs(rng, f'more{index}.')}",
            )
        )
        for index in range(rng.randint(0, 6))
    ]
    document: str = _toml_pairs(rng, "") + "\n".join(sections)
    line_endings: str = rng.choice((document, document, document.replace("\n", "\r\n")))
    return rng.choice(BYTE_ORDER_MARKS) + line_endings


TOML_NAMESPACE_NAMES: tuple[str, ...] = (
    "a", "b", "a.b", "a.c", "b.a", "a.b.c", "a.b.c.d", "b.c.d", '"a".b', "a.'b'.c",
)  # fmt: skip
TOML_NAMESPACE_VALUES: tuple[str, ...] = (
    "1", "{}", "{x = 1}", "{c = {d = 1}}", "[]", "[{x = 1}]", "{b.c = 1}", "[1, 2]",
)  # fmt: skip
TOML_NAMESPACE_STATEMENTS: tuple[Callable[[random.Random], str], ...] = (
    lambda rng: f"[{rng.choice(TOML_NAMESPACE_NAMES)}]",
    lambda rng: f"[[{rng.choice(TOML_NAMESPACE_NAMES)}]]",
    lambda rng: f"{rng.choice(TOML_NAMESPACE_NAMES)} = {rng.choice(TOML_NAMESPACE_VALUES)}",
    lambda rng: f"{rng.choice(TOML_NAMESPACE_NAMES)}.k{rng.randint(0, 2)} = 1",
    lambda rng: (
        f"x = {{{rng.choice(TOML_NAMESPACE_NAMES)} = 1, {rng.choice(TOML_NAMESPACE_NAMES)} = 2}}"
    ),
)


def toml_namespace_document(*, rng: random.Random) -> str:
    """Return statements that reopen tables, arrays of tables and dotted keys in random orders."""

    return "\n".join(rng.choice(TOML_NAMESPACE_STATEMENTS)(rng) for _ in range(rng.randint(1, 8)))


TOML_DOCUMENT_GENERATORS: dict[str, Callable[[random.Random], str]] = {
    "toml": lambda rng: toml_document(rng=rng),
    "toml namespaces": lambda rng: toml_namespace_document(rng=rng),
}


def _float_canonical(value: float) -> list[object]:
    bits: str = str(struct.unpack("<Q", struct.pack("<d", value))[0])
    return ["float", {True: "nan", False: bits}[math.isnan(value)]]


OFFSET_SECONDS: dict[type, Callable[[Any], int | None]] = {
    type(None): lambda offset: None,
    datetime.timedelta: lambda offset: int(offset.total_seconds()),
}


def _utc_offset(value: datetime.datetime) -> int | None:
    offset: datetime.timedelta | None = value.utcoffset()
    return OFFSET_SECONDS[type(offset)](offset)


CANONICAL: dict[type, Callable[[Any], object]] = {
    type(None): lambda value: ["null"],
    bool: lambda value: ["bool", value],
    int: lambda value: ["int", str(value)],
    float: _float_canonical,
    str: lambda value: ["str", value],
    datetime.date: lambda value: ["date", [value.year, value.month, value.day]],
    datetime.datetime: lambda value: [
        "datetime",
        [value.year, value.month, value.day],
        [value.hour, value.minute, value.second, value.microsecond],
        _utc_offset(value),
    ],
    datetime.time: lambda value: [
        "time",
        [value.hour, value.minute, value.second, value.microsecond],
    ],
    list: lambda value: ["list", [canonical(item) for item in value]],
    dict: lambda value: ["map", [[canonical(key), canonical(item)] for key, item in value.items()]],
}


def canonical(value: object) -> object:
    """Return the tagged canonical form the native oracle hooks also produce."""

    return CANONICAL[type(value)](value)


def python_toml_outcome(*, text: str) -> object:
    """Return `tomllib`'s canonical value, or the rejection marker when it raises."""

    outcome: list[object] = [PYTHON_ERROR]
    with suppress(tomllib.TOMLDecodeError, ValueError):
        outcome[0] = canonical(tomllib.loads(text))
    return outcome[0]


def native_outcome(payload: str) -> object:
    """Return the native canonical value, or the marker of its failure kind."""

    parsed: object = json.loads(payload)
    return {list: parsed, dict: DEFERRED}[type(parsed)]


def native_toml_outcome(*, text: str) -> object:
    """Return the native TOML loader's outcome for `text`."""

    return native_outcome(_native._oracle_toml_load(text))


def repository_files(*, pattern: str) -> list[Path]:
    """Return tracked-looking repository files matching `pattern`, outside build directories."""

    return sorted(
        filter(
            lambda path: EXCLUDED_DIRECTORIES.isdisjoint(path.relative_to(REPOSITORY_ROOT).parts),
            REPOSITORY_ROOT.glob(pattern),
        )
    )


def _python_project_fields(project: ProjectConfig, local: LocalConfig) -> dict[str, object]:
    return {
        "name": project.name,
        "adapter": project.adapter,
        "default_target": project.default_target,
        "sql_analysis": project.settings.sql_analysis,
        "require_sql_analysis": project.settings.require_sql_analysis,
        "enforce_placement": project.scopes.enforce_placement,
        "enforce_explicit_references": project.references.enforce_explicit,
        "vars": [list(item) for item in project.vars.items()],
        "path_default_keys": list(project.path_defaults),
        "target_names": list(project.targets),
        "local_target": local.target,
        "local_adapter": local.adapter,
        "local_sql_analysis": {True: local.settings.sql_analysis, False: None}[
            "sql_analysis" in local.setting_overrides
        ],
        "local_vars": [list(item) for item in local.vars.items()],
        "local_target_names": list(local.targets),
    }


def python_project_outcome(*, project_dir: Path) -> object:
    """Return the discovery fields Python's loaders read, or the rejection marker."""

    outcome: list[object] = [PYTHON_ERROR]
    with suppress(Exception):
        outcome[0] = _python_project_fields(
            load_project_config(project_dir=project_dir), load_local_config(project_dir=project_dir)
        )
    return outcome[0]


def native_project_outcome(*, project_dir: Path) -> object:
    """Return the discovery fields the native reader reads, or its failure marker."""

    parsed: dict[str, object] = json.loads(_native._oracle_project_config(str(project_dir)))
    return {True: DEFERRED, False: parsed}["error" in parsed]


def deferred_valid_count(*, expected: list[object], actual: list[object]) -> int:
    """Return how many documents Python accepts but the native reader defers back to Python."""

    return sum(
        map(
            lambda python, native: native == DEFERRED and python not in UNCHECKED_PYTHON_OUTCOMES,
            expected,
            actual,
        )
    )


def _is_harmful(expected: object, actual: object) -> bool:
    return actual != DEFERRED and actual != expected


def harmful_mismatches(
    *, inputs: list[object], expected: list[object], actual: list[object]
) -> list[tuple[object, object, object]]:
    """Return the first few cases where the native reader accepts a different result.

    A native failure defers the file to the Python loader, so only an accepted value that
    differs from Python's outcome, including accepting what Python rejects, is harmful.
    """

    return list(
        compress(zip(inputs, expected, actual, strict=True), map(_is_harmful, expected, actual))
    )[:3]
