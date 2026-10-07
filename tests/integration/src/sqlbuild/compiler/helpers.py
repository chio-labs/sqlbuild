"""Seeded generators and Python-side results shared by the native oracle tests."""

from __future__ import annotations

import json
import math
import random
import struct
from collections.abc import Callable
from contextlib import suppress
from itertools import compress
from operator import ne
from pathlib import Path

import orjson

from sqlbuild import _native
from tests.integration.src.sqlbuild.compiler._test_types import JsonOracleTestCase

NASTY_FLOATS: tuple[float, ...] = (
    0.0,
    -0.0,
    math.nan,
    math.inf,
    -math.inf,
    5e-324,
    -5e-324,
    2.2250738585072014e-308,
    1.7976931348623157e308,
    1e16,
    9999999999999998.0,
    1e15,
    1e-4,
    1e-5,
    9.999999999999999e-5,
    0.1,
    0.30000000000000004,
    1 / 3,
    2.0**53,
    2.0**53 + 2,
    1e22,
    1e-7,
    1.5e-6,
    100.0,
    -123456.789,
)
NASTY_INTEGERS: tuple[int, ...] = (
    0,
    -1,
    2**31,
    2**53 + 1,
    2**63 - 1,
    2**63,
    -(2**63),
    -(2**63) - 1,
    2**64 - 1,
    2**64,
    10**40,
    -(10**40),
)
CHARACTER_RANGES: tuple[tuple[int, int], ...] = (
    (0x20, 0x7E),
    (0x20, 0x7E),
    (0x20, 0x7E),
    (0x00, 0x1F),
    (0x7F, 0xA0),
    (0xA1, 0x24F),
    (0x2000, 0x206F),
    (0x4E00, 0x4E80),
    (0xE000, 0xE010),
    (0xFFF0, 0xFFFF),
    (0x1F600, 0x1F64F),
    (0x10FFF0, 0x10FFFF),
    (0x22, 0x22),
    (0x5C, 0x5C),
    (0x2028, 0x2029),
    (0xFEFF, 0xFEFF),
)
LINE_BREAKS: tuple[str, ...] = ("\n", "\r\n", "\r", "\t", "\r\r\n")
INVALID_UTF8: tuple[bytes, ...] = (b"\xff", b"\xc3", b"\xed\xa0\x80", b"\xf4\x90\x80\x80")
MAX_JSON_DEPTH: int = 4


def random_character(*, rng: random.Random) -> str:
    """Return one code point from a range chosen to stress escaping and offsets."""

    low, high = rng.choice(CHARACTER_RANGES)
    return chr(rng.randint(low, high))


def random_text(*, rng: random.Random, max_length: int) -> str:
    """Return a string mixing ASCII, controls, non-BMP and other awkward code points."""

    return "".join(random_character(rng=rng) for _ in range(rng.randint(0, max_length)))


def _float_from_bits(rng: random.Random) -> float:
    return struct.unpack("<d", rng.getrandbits(64).to_bytes(8, "little"))[0]


def _float_from_decimal(rng: random.Random) -> float:
    mantissa: int = rng.randint(1, 10 ** rng.randint(1, 17))
    return float(f"{rng.choice('-+')}{mantissa}e{rng.randint(-340, 300)}")


FLOAT_GENERATORS: tuple[Callable[[random.Random], float], ...] = (
    lambda rng: rng.choice(NASTY_FLOATS),
    _float_from_bits,
    _float_from_decimal,
)
INTEGER_GENERATORS: tuple[Callable[[random.Random], int], ...] = (
    lambda rng: rng.choice(NASTY_INTEGERS) + rng.randint(-2, 2),
    lambda rng: rng.randint(-(2 ** rng.randint(1, 140)), 2 ** rng.randint(1, 140)),
)


def random_float(*, rng: random.Random) -> float:
    """Return a float from the nasty pool, random bits, or a random decimal."""

    return rng.choice(FLOAT_GENERATORS)(rng)


def random_integer(*, rng: random.Random) -> int:
    """Return an integer near the 32- and 64-bit boundaries or of arbitrary size."""

    return rng.choice(INTEGER_GENERATORS)(rng)


def _json_list(rng: random.Random, depth: int) -> object:
    return [random_json_value(rng=rng, depth=depth - 1) for _ in range(rng.randint(0, 4))]


def _json_dict(rng: random.Random, depth: int) -> object:
    return {
        random_text(rng=rng, max_length=6): random_json_value(rng=rng, depth=depth - 1)
        for _ in range(rng.randint(0, 4))
    }


JSON_SCALAR_GENERATORS: tuple[Callable[[random.Random, int], object], ...] = (
    lambda rng, depth: None,
    lambda rng, depth: rng.random() < 0.5,
    lambda rng, depth: random_integer(rng=rng),
    lambda rng, depth: random_float(rng=rng),
    lambda rng, depth: random_text(rng=rng, max_length=12),
)
JSON_GENERATORS: tuple[Callable[[random.Random, int], object], ...] = (
    *JSON_SCALAR_GENERATORS,
    _json_list,
    _json_dict,
    _json_list,
    _json_dict,
)


def random_json_value(*, rng: random.Random, depth: int) -> object:
    """Return a random JSON-compatible Python value, preferring containers above the leaves."""

    available: int = len(JSON_SCALAR_GENERATORS) + 4 * min(depth, 1)
    return rng.choice(JSON_GENERATORS[:available])(rng, depth)


def _float_bits(value: float) -> str:
    return str(struct.unpack("<Q", struct.pack("<d", value))[0])


TAGGERS: dict[type, Callable[[object], list[object]]] = {
    type(None): lambda value: ["null", None],
    bool: lambda value: ["bool", value],
    int: lambda value: ["int", str(value)],
    float: lambda value: ["float", _float_bits(value)],
    str: lambda value: ["str", value],
    list: lambda value: ["list", [tagged(item) for item in value]],
    dict: lambda value: [
        "dict",
        [[key, tagged(item)] for key, item in value.items()],
    ],
}


def tagged(value: object) -> list[object]:
    """Return the tagged form the native JSON oracle hook decodes."""

    return TAGGERS[type(value)](value)


def python_json_text(*, value: object, test_case: JsonOracleTestCase) -> str:
    """Return Python's serializer output, or the name of the failure it raises."""

    outcome: list[str] = [f"error:{SERIALIZER_FAILURES[test_case.serializer]}"]
    with suppress(ValueError, TypeError):
        outcome[0] = PYTHON_SERIALIZERS[test_case.serializer](value, test_case)
    return outcome[0]


def _stdlib_dumps(value: object, test_case: JsonOracleTestCase) -> str:
    return json.dumps(
        value,
        indent=test_case.indent,
        separators=test_case.separators,
        ensure_ascii=test_case.ensure_ascii,
        sort_keys=test_case.sort_keys,
        allow_nan=test_case.allow_nan,
    )


PYTHON_SERIALIZERS: dict[str, Callable[[object, JsonOracleTestCase], str]] = {
    "stdlib": _stdlib_dumps,
    "orjson": lambda value, test_case: orjson.dumps(value, option=test_case.orjson_option).decode(),
}
SERIALIZER_FAILURES: dict[str, str] = {"stdlib": "NonFiniteFloat", "orjson": "IntegerOutOfRange"}


INDENT_TEXT: dict[type, Callable[[object], object]] = {
    int: lambda width: " " * width,
    str: lambda text: text,
    type(None): lambda nothing: nothing,
}


def native_json_text(*, value: object, test_case: JsonOracleTestCase) -> str:
    """Return the native emitter's output for the same value and configuration."""

    default_separators: tuple[str, str] = ((", ", ": "), (",", ": "))[test_case.indent is not None]
    item_separator, key_separator = test_case.separators or default_separators
    indent: object = INDENT_TEXT[type(test_case.indent)](test_case.indent)
    specs: dict[str, dict[str, object]] = {
        "stdlib": {
            "indent": indent,
            "separators": {"item": item_separator, "key": key_separator},
            "ensure_ascii": test_case.ensure_ascii,
            "sort_keys": test_case.sort_keys,
            "allow_nan": test_case.allow_nan,
        },
        "orjson": {
            "orjson": {
                "indent_2": bool(test_case.orjson_option & orjson.OPT_INDENT_2),
                "sort_keys": bool(test_case.orjson_option & orjson.OPT_SORT_KEYS),
            }
        },
    }
    spec: dict[str, object] = specs[test_case.serializer]
    return _native._oracle_json_dumps(json.dumps(spec), json.dumps(tagged(value)))


def mismatches(
    *, inputs: list[object], expected: list[object], actual: list[object]
) -> list[tuple[object, object, object]]:
    """Return the first few `(input, expected, actual)` triples that differ."""

    return list(compress(zip(inputs, expected, actual, strict=True), map(ne, expected, actual)))[:3]


def authored_bytes(*, rng: random.Random) -> bytes:
    """Return valid UTF-8 text with every newline convention, tabs and non-ASCII."""

    parts: list[str] = [
        random_text(rng=rng, max_length=8) + rng.choice(LINE_BREAKS)
        for _ in range(rng.randint(0, 12))
    ]
    return "".join(parts).encode("utf-8")


def invalid_authored_bytes(*, rng: random.Random) -> bytes:
    """Return authored bytes with one invalid UTF-8 sequence inserted."""

    data: bytes = authored_bytes(rng=rng)
    cut: int = rng.randint(0, len(data))
    return data[:cut] + rng.choice(INVALID_UTF8) + data[cut:]


def python_positions(*, text: str, char_offsets: list[int]) -> list[tuple[int, int, int]]:
    """Return `(char_offset, line, column)` with SQLBuild's Python line and column arithmetic."""

    return [
        (
            offset,
            text.count("\n", 0, offset) + 1,
            offset - (text.rfind("\n", 0, offset) + 1) + 1,
        )
        for offset in char_offsets
    ]


def random_char_offsets(*, rng: random.Random, text: str) -> list[int]:
    """Return sorted random code-point offsets into `text`, including its end."""

    return sorted(rng.randint(0, len(text)) for _ in range(8))


def utf8_offsets(*, text: str, char_offsets: list[int]) -> list[int]:
    """Return the UTF-8 byte offset of each code-point offset into `text`."""

    return [len(text[:offset].encode("utf-8")) for offset in char_offsets]


def python_read_text(*, path: Path, data: bytes) -> str:
    """Write `data` and read it back the way SQLBuild reads authored files."""

    path.write_bytes(data)
    return path.read_text(encoding="utf-8")


CLEANDOC_FRAGMENTS: tuple[str, ...] = (
    "", " ", "  ", "\t", " \t", "\u3000", "\x0b", "\x1c", "\xa0", "\r", "\n", "\n", "\n\n",
    "SELECT 1", "a", "é", "x\ty", "--c",
)  # fmt: skip
MUTATION_ALPHABET: str = "abcdefghijklmnopqrstuvwxyz_0é"


def _insert(*, rng: random.Random, word: list[str], position: int) -> None:
    word.insert(position, rng.choice(MUTATION_ALPHABET))


def _delete(*, rng: random.Random, word: list[str], position: int) -> None:
    _ = rng
    del word[position : position + 1]


def _substitute(*, rng: random.Random, word: list[str], position: int) -> None:
    word[position : position + 1] = [rng.choice(MUTATION_ALPHABET)]


MUTATIONS: tuple[Callable[..., None], ...] = (_insert, _delete, _substitute)


def cleandoc_text(*, rng: random.Random) -> str:
    """Return a body mixing indentation, tabs, Unicode spaces and blank lines."""

    return "".join(rng.choices(CLEANDOC_FRAGMENTS, k=rng.randint(0, 24)))


def mutated_word(*, rng: random.Random, candidates: list[str]) -> str:
    """Return a candidate with a few random insertions, deletions and substitutions."""

    word: list[str] = list(rng.choice(candidates))
    for _ in range(rng.randint(0, 4)):
        rng.choice(MUTATIONS)(rng=rng, word=word, position=rng.randint(0, len(word)))
    return "".join(word)
