"""Seeded YAML and TOML generators and canonical values for the native configuration oracles."""

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
from typing import Any, cast

import pytest
import yaml

from sqlbuild import _native
from sqlbuild.compiler.discovery._helpers.filesystem.aggregation import (
    build_tolerant_scope_discovery,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import native_payload_error
from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.compiler.discovery.classes.selected_contract_input_discoverer import (
    SelectedContractInputDiscoverer,
)
from sqlbuild.compiler.discovery.main._model_description_inputs import (
    discover_model_description_inputs,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredEnumFile,
    DiscoveredProjectInputs,
    TolerantScopeDiscovery,
)
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig
from tests.integration.src.sqlbuild.compiler.helpers import random_float, random_text

REPOSITORY_ROOT: Path = Path(__file__).resolve().parents[6]
EXCLUDED_DIRECTORIES: frozenset[str] = frozenset({".venv", "node_modules", "target", ".git"})
PYTHON_ERROR: dict[str, str] = {"error": "rejected"}
DEFERRED: dict[str, str] = {"error": "deferred to Python"}
LOADERS_DISAGREE: dict[str, str] = {"error": "PyYAML and LibYAML disagree"}
UNCHECKED_PYTHON_OUTCOMES: tuple[dict[str, str], ...] = (PYTHON_ERROR, LOADERS_DISAGREE)
UNDECODABLE_BYTES: tuple[int, ...] = (
    0x80, 0x9F, 0xA0, 0xBF, 0xC0, 0xC1, 0xC2, 0xE0, 0xE2, 0xED, 0xF0, 0xF4, 0xF5, 0xFF,
)  # fmt: skip
YAML_LINE_BREAKS: dict[int, None] = {0x85: None, 0x2028: None, 0x2029: None}
SCALAR_FRAGMENTS: tuple[str, ...] = (
    "0", "1", "7", "8", "9", "00", "12", "59", "60", "_", ".", ":", "e", "E", "e+", "E-",
    "+", "-", "x", "b", "o", "0x", "0b", "0o", "a", "f", "F", "inf", "Inf", ".inf", ".nan",
    "NaN", "yes", "Yes", "NO", "on", "ON", "off", "true", "True", "FALSE", "null", "Null",
    "NULL", "~", "<<", "=", "y", "n", "T", "t", " ", "Z", "2001", "-12", "-2", "-14", "T21",
    ":59", ":43", ".10", "-05:00", "+5", " -5", "1_0", "é", "#", "'", '"',
)  # fmt: skip
KNOWN_SCALARS: tuple[str, ...] = (
    "yes", "No", "oN", "~", "", "<<", "=", "017", "0o17", "08", "0b101", "0x1F", "0x_",
    "1_000", "190:20:30", "1:60", "-190:20:30.5", "1e5", "1.0e5", "1.0e+5", ".5", "5.", "+.5",
    "-0.0", ".NaN", "-.inf", "2001-12-14", "2001-1-4", "2002-02-30", "2001-12-14t21:59:43.10-05:00",
    "2001-12-14 21:59:43.10 -5", "2001-12-14 21:59:43.1234567Z", "2001-12-14T24:00:00",
    "2001-12-14 1:02:03 +23:59", "99999999999999999999999", "-0b_1", "0_", "_1", "1__2.3_",
)  # fmt: skip
SCALAR_CONTEXTS: tuple[str, ...] = (
    "key: {plain}",
    "- {plain}",
    "[{plain}, 1]",
    "{plain}: value",
    "key: '{single}'",
    'key: "{double}"',
    "key: ! {plain}",
    "key: ! '{single}'",
    "key: !!int {plain}",
    "key: !!float {plain}",
    "key: !!bool {plain}",
    "key: !!str {plain}",
    "key: !!null {plain}",
    "key: !!timestamp {plain}",
    "? {plain}\n: 1",
)
DOCUMENT_TEMPLATES: tuple[str, ...] = (
    "base{n}: &anchor{n}\n  shared: {a}\n  other: {b}\nitem{n}:\n  <<: *anchor{n}\n  other: {c}\n",
    "list{n}:\n  - &item{n} {a}\n  - *item{n}\n  - [{b}, {c}]\n",
    "merged{n}:\n  <<: [{{x: {a}}}, {{x: {b}, y: {c}}}]\n  z: {a}\n",
    "flow{n}: {{k{n}: {a}, j{n}: [{b}, {{m: {c}}}]}}\n",
    "literal{n}: |\n  {a}\n   {b}\n\n  {c}\nfolded{n}: >-\n  {a}\n  {b}\n",
    "? complex{n}\n: {a}\n# comment {b}\nafter{n}: {c}  # trailing\n",
    "{a}: first\n{a}: second\n",
    "keep{n}: |+\n  {a}\n\n  {b}\n\n",
    "strip{n}: >-\n  {a}\n\n   {b}\n  \n",
    "seq{n}:\n- |\n  {a}\n- >+\n  {b}\n \n",
    "nested{n}:\n  inner: |\n    {a}\n     {b}\n   \n",
    "indented{n}:\n  - |2-\n     {a}\n    {c}\n",
    "empty{n}: |\n   \n\nafter{n}: {b}\n",
)
DOCUMENT_TAILS: tuple[str, ...] = (
    "", "\n", "\n\n", " ", "  ", "\n ", "\n  ", "\n   \n", "  \n  ", "\n# end", "\n...\n",
)  # fmt: skip
BYTE_ORDER_MARKS: tuple[str, ...] = ("",) * 19 + ("\ufeff",)


def yaml_text(*, rng: random.Random, max_length: int) -> str:
    """Return random text without the line breaks only YAML 1.1 recognizes."""

    return random_text(rng=rng, max_length=max_length).translate(YAML_LINE_BREAKS)


def random_scalar(*, rng: random.Random) -> str:
    """Return a near-miss plain scalar built from resolver-sensitive fragments."""

    pieces: list[str] = [rng.choice(SCALAR_FRAGMENTS) for _ in range(rng.randint(1, 4))]
    return rng.choice(("".join(pieces), rng.choice(KNOWN_SCALARS)))


def scalar_document(*, rng: random.Random) -> str:
    """Return a scalar embedded in a plain, quoted or tagged YAML context."""

    scalar: str = random_scalar(rng=rng)
    return rng.choice(SCALAR_CONTEXTS).format(
        plain=scalar, single=scalar.replace("'", "''"), double=scalar.replace('"', "'")
    )


def anchored_document(*, rng: random.Random) -> str:
    """Return a block document with anchors, aliases, merge keys, literals and comments."""

    return "".join(
        rng.choice(DOCUMENT_TEMPLATES).format(
            n=index, a=random_scalar(rng=rng), b=random_scalar(rng=rng), c=random_scalar(rng=rng)
        )
        for index in range(rng.randint(1, 4))
    )


def _yaml_key(rng: random.Random) -> object:
    return rng.choice(
        (
            yaml_text(rng=rng, max_length=6),
            rng.randint(-5, 5),
            rng.random() < 0.5,
            None,
            datetime.date(2000 + rng.randint(0, 30), rng.randint(1, 12), rng.randint(1, 28)),
            yaml_text(rng=rng, max_length=12),
        )
    )


def _yaml_datetime(rng: random.Random) -> object:
    offset: datetime.timedelta = datetime.timedelta(minutes=rng.randint(-1439, 1439))
    zone: datetime.tzinfo | None = rng.choice((None, datetime.timezone(offset), datetime.UTC))
    return datetime.datetime(
        rng.randint(1, 9999),
        rng.randint(1, 12),
        rng.randint(1, 28),
        rng.randint(0, 23),
        rng.randint(0, 59),
        rng.randint(0, 59),
        rng.choice((0, rng.randint(0, 999_999))),
        tzinfo=zone,
    )


YAML_SCALARS: tuple[Callable[[random.Random], object], ...] = (
    lambda rng: None,
    lambda rng: rng.random() < 0.5,
    lambda rng: rng.randint(-(2**70), 2**70),
    lambda rng: random_float(rng=rng),
    lambda rng: yaml_text(rng=rng, max_length=30),
    lambda rng: random_scalar(rng=rng),
    lambda rng: datetime.date(rng.randint(1, 9999), rng.randint(1, 12), rng.randint(1, 28)),
    _yaml_datetime,
)


def _yaml_list(rng: random.Random, depth: int) -> object:
    return [random_yaml_value(rng=rng, depth=depth - 1) for _ in range(rng.randint(0, 4))]


def _yaml_dict(rng: random.Random, depth: int) -> object:
    return {
        _yaml_key(rng): random_yaml_value(rng=rng, depth=depth - 1)
        for _ in range(rng.randint(0, 4))
    }


YAML_GENERATORS: tuple[Callable[[random.Random, int], object], ...] = (
    *(lambda rng, depth, scalar=scalar: scalar(rng) for scalar in YAML_SCALARS),
    _yaml_list,
    _yaml_dict,
    _yaml_list,
    _yaml_dict,
)


def random_yaml_value(*, rng: random.Random, depth: int) -> object:
    """Return a random value of the types PyYAML's safe dumper writes."""

    available: int = len(YAML_SCALARS) + 4 * min(depth, 1)
    return rng.choice(YAML_GENERATORS[:available])(rng, depth)


def dumped_document(*, rng: random.Random) -> str:
    """Return a document written by PyYAML's safe dumper in a random style."""

    return yaml.safe_dump(
        random_yaml_value(rng=rng, depth=3),
        default_flow_style=rng.choice((None, True, False)),
        default_style=rng.choice((None, None, '"', "'")),
        width=rng.choice((12, 80, 4096)),
        allow_unicode=rng.random() < 0.5,
        explicit_start=rng.random() < 0.3,
        sort_keys=False,
    )


def _alias_chain(links: int) -> str:
    return "a0: &a0 [x]\n" + "".join(
        f"a{link}: &a{link} [*a{link - 1}]\n" for link in range(1, links)
    )


def _billion_laughs(levels: int) -> str:
    return 'a0: &a0 "lol"\n' + "".join(
        f"a{level}: &a{level} [{', '.join([f'*a{level - 1}'] * 10)}]\n"
        for level in range(1, levels)
    )


def _merge_chain(levels: int) -> str:
    return "m0: &m0 {k0: 1}\n" + "".join(
        f"m{level}: &m{level} {{<<: [*m{level - 1}, *m{level - 1}], k{level}: 1}}\n"
        for level in range(1, levels)
    )


HOSTILE_YAML_DOCUMENTS: dict[str, Callable[[], str]] = {
    "alias chain": lambda: _alias_chain(10_000),
    "billion laughs": lambda: _billion_laughs(12),
    "merge chain": lambda: _merge_chain(30),
    "deep flow": lambda: "a: " + "[" * 100_000 + "]" * 100_000,
    "deep block": lambda: "- " * 100_000,
    "long integer": lambda: "a: " + "9" * 4_301,
}
LARGE_YAML_DOCUMENTS: dict[str, Callable[[], str]] = {
    "flow mapping": lambda: "{" + ", ".join(f"k{index}: {index}" for index in range(100_000)) + "}",
    "flow sequence": lambda: "[" + ",".join("1" for _ in range(200_000)) + "]",
    "anchored flow sequence": lambda: (
        "[" + ", ".join(f"&a{index} x{index}" for index in range(50_000)) + "]"
    ),
}
HOSTILE_TOML_DOCUMENTS: dict[str, Callable[[], str]] = {
    "deep arrays": lambda: "a = " + "[" * 10_000 + "]" * 10_000,
    "deep inline tables": lambda: "a = " + "{b = " * 10_000 + "}" * 10_000,
    "long dotted key": lambda: "a" + ".a" * 100_000 + " = 1",
    "long table header": lambda: "[a" + ".a" * 100_000 + "]",
}


def finished_document(*, rng: random.Random, text: str) -> str:
    """Return `text` with or without its final line break, trailing blank lines or a BOM."""

    trimmed: str = text.rstrip("\n")
    ending: str = rng.choice((text, trimmed, trimmed + rng.choice(DOCUMENT_TAILS)))
    return rng.choice(BYTE_ORDER_MARKS) + ending


LONG_KEY_CONTEXTS: tuple[str, ...] = (
    "{key}: 1\n", "{{{key}: 1}}\n", "[{key}: 1]\n", "a:\n  {key} : 1\n", "'{key}': 1\n",
    "&k {key}: 1\n", "? {key}\n: 1\n", "x: {{{key}: 1, b: 2}}\n",
)  # fmt: skip


def long_key_document(*, rng: random.Random) -> str:
    """Return a document whose key length straddles the 1024-character simple-key limit."""

    key: str = rng.choice(("a", "0x", "é")) * rng.randint(990, 1040)
    return rng.choice(LONG_KEY_CONTEXTS).format(key=key)


YAML_DOCUMENT_GENERATORS: dict[str, Callable[[random.Random], str]] = {
    "long keys": lambda rng: long_key_document(rng=rng),
    "scalars": lambda rng: finished_document(rng=rng, text=scalar_document(rng=rng)),
    "anchors": lambda rng: finished_document(rng=rng, text=anchored_document(rng=rng)),
    "dumped": lambda rng: finished_document(rng=rng, text=dumped_document(rng=rng)),
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


def python_yaml_outcome(*, text: str, loader: type[yaml.SafeLoader]) -> object:
    """Return PyYAML's canonical value, or the rejection marker when it raises."""

    outcome: list[object] = [PYTHON_ERROR]
    with suppress(
        yaml.YAMLError, ValueError, TypeError, OverflowError, AttributeError, KeyError, IndexError
    ):
        outcome[0] = canonical(yaml.load(text, Loader=loader))
    return outcome[0]


def expected_yaml_outcome(*, text: str) -> object:
    """Return the value both PyYAML loaders agree on, or the marker that native must defer."""

    pure: object = python_yaml_outcome(text=text, loader=yaml.SafeLoader)
    libyaml: object = python_yaml_outcome(text=text, loader=yaml.CSafeLoader)
    return {True: pure, False: LOADERS_DISAGREE}[pure == libyaml]


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


def native_yaml_outcome(*, text: str) -> object:
    """Return the native YAML loader's outcome for `text`."""

    return native_outcome(_native._oracle_yaml_load(text))


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


PROJECT_CONFIG: str = 'name = "orders"\nadapter = "duckdb"\n'


def native_yaml_tags_and_values(
    *, project_dir: Path, relative_paths: list[str]
) -> tuple[list[object], bool]:
    """Return each file's native tag and whether every natively loaded value equals LibYAML's."""

    payloads: list[tuple[object, ...]] = cast(
        list[tuple[object, ...]],
        _native.load_yaml_files(
            {"project_dir": str(project_dir), "display_prefix": "", "kind": "source"},
            relative_paths,
            _native.NativeProjectTree(str(project_dir)),
        ),
    )
    rows: list[tuple[object, ...]] = list(payloads)
    loaded: list[tuple[object, ...]] = list(compress(rows, [row[0] == "ok" for row in rows]))
    expected: list[object] = [yaml.load(str(row[1]), Loader=yaml.CSafeLoader) for row in loaded]
    return [row[0] for row in rows], [row[2] for row in loaded] == expected


class FailureCapture:
    """Swallow and keep the discovery failure a block raises."""

    def __init__(self) -> None:
        self.failure: BaseException | None = None

    def __enter__(self) -> FailureCapture:
        return self

    def __exit__(self, error_type: object, error: BaseException | None, traceback: object) -> bool:
        self.failure = error
        return isinstance(error, OSError | ValueError | RuntimeError)


def write_project(*, project_dir: Path, files: tuple[tuple[str, bytes], ...]) -> None:
    """Write a project config and authored files."""

    project_dir.mkdir(parents=True, exist_ok=True)
    _ = (project_dir / "sqlbuild_project.toml").write_text(PROJECT_CONFIG, encoding="utf-8")
    for relative_path, data in files:
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(data)


def stage_outcome(*, project_dir: Path, engine: str, monkeypatch: pytest.MonkeyPatch) -> object:
    """Return the rendered discovery stage under `engine` with its failure type and message."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
    capture: FailureCapture = FailureCapture()
    rendered: list[object] = [None]
    with capture:
        rendered[0] = render_stage_capture(discover_project_inputs(project_dir=project_dir))
    return (rendered[0], type(capture.failure).__name__, str(capture.failure))


def random_undecodable_bytes(*, rng: random.Random) -> bytes:
    """Return text bytes with UTF-8 sequences cut, corrupted or replaced by invalid bytes."""

    text: bytes = random_text(rng=rng, max_length=12).encode("utf-8")
    cut: int = rng.randint(0, len(text))
    noise: bytes = bytes(rng.choice(UNDECODABLE_BYTES) for _ in range(rng.randint(0, 3)))
    return rng.choice((text[:cut] + noise + text[cut:], text[:cut], noise + text))


def native_read_outcomes(*, project_dir: Path, relative_paths: list[str]) -> list[object]:
    """Return the type and text of the read error native reading reports for each file, if any."""

    payloads: list[tuple[object, ...]] = cast(
        list[tuple[object, ...]],
        _native.load_yaml_files(
            {"project_dir": str(project_dir), "display_prefix": "", "kind": "source"},
            relative_paths,
            _native.NativeProjectTree(str(project_dir)),
        ),
    )
    errors: list[Exception | None] = [
        native_payload_error(payload=payload, file_path=project_dir / path)
        for payload, path in zip(payloads, relative_paths, strict=True)
    ]
    return [
        {True: (type(error).__name__, str(error)), False: ("NoneType", "None")}[
            isinstance(error, UnicodeError | OSError)
        ]
        for error in errors
    ]


def python_read_outcomes(*, project_dir: Path, relative_paths: list[str]) -> list[object]:
    """Return the type and text of the error `Path.read_text` raises for each file, if any."""

    outcomes: list[object] = []
    for relative_path in relative_paths:
        capture: FailureCapture = FailureCapture()
        with capture:
            _ = (project_dir / relative_path).read_text(encoding="utf-8")
        outcomes.append((type(capture.failure).__name__, str(capture.failure)))
    return outcomes


def compile_failure(*, project_dir: Path) -> tuple[str, str]:
    """Return the type and text of the error project discovery raises."""

    capture: FailureCapture = FailureCapture()
    with capture:
        _ = discover_project_inputs(project_dir=project_dir)
    return type(capture.failure).__name__, str(capture.failure)


def discovery_failure_with_help(*, project_dir: Path) -> tuple[str, str, bool]:
    """Return the type and text of the error project discovery raises, and whether it has help."""

    capture: FailureCapture = FailureCapture()
    with capture:
        _ = discover_project_inputs(project_dir=project_dir)
    return (
        type(capture.failure).__name__,
        str(capture.failure),
        getattr(capture.failure, "help", None) is not None,
    )


def tolerant_scope_fault_outcome(*, project_dir: Path) -> tuple[object, ...]:
    """Return tolerant scope discovery's model and source paths and its per-file faults."""

    discovery: TolerantScopeDiscovery = build_tolerant_scope_discovery(project_dir=project_dir)
    return (
        *_inputs_paths(discovery.discovered_inputs),
        tuple(
            (str(fault.path), fault.message)
            for fault in (*discovery.resource_faults, *discovery.relationship_faults)
        ),
    )


def description_inputs_outcome(*, project_dir: Path) -> tuple[object, ...]:
    """Return the model and source paths model description resolution reads, without faults."""

    return (*_inputs_paths(discover_model_description_inputs(project_dir=project_dir)), ())


def selected_contract_outcome(*, project_dir: Path) -> tuple[object, ...]:
    """Return the model and source paths selected-contract discovery reads for `orders`."""

    inputs: DiscoveredProjectInputs = SelectedContractInputDiscoverer.discover(
        project_dir=project_dir,
        selected_test_paths=frozenset(),
        referenced_model_names=frozenset({"orders"}),
    )
    return (*_inputs_paths(inputs), ())


def _inputs_paths(inputs: DiscoveredProjectInputs) -> tuple[object, ...]:
    return (
        tuple(model.relative_path.as_posix() for model in inputs.model_files),
        tuple(source.relative_path.as_posix() for source in inputs.source_files),
    )


def declared_enums_outcome(*, project_dir: Path) -> tuple[object, ...]:
    """Return each discovered enum file with the enum names it declares, and the model paths."""

    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    return (
        tuple(_declared_enum_names(enum_file) for enum_file in inputs.enum_files),
        tuple(model.relative_path.as_posix() for model in inputs.model_files),
    )


def _declared_enum_names(enum_file: DiscoveredEnumFile) -> tuple[str, tuple[str, ...]]:
    return (
        enum_file.relative_path.as_posix(),
        tuple(declaration.name for declaration in enum_file.declarations),
    )
