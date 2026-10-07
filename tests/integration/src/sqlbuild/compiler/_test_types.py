from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JsonOracleTestCase:
    """One Python serializer configuration compared with the native emitter on seeded values."""

    description: str
    serializer: str
    seed: int
    case_count: int
    indent: int | str | None = None
    separators: tuple[str, str] | None = None
    ensure_ascii: bool = True
    sort_keys: bool = False
    allow_nan: bool = True
    orjson_option: int = 0
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class TextOracleTestCase:
    """Seeded authored files whose native decoding and positions are compared with Python."""

    description: str
    seed: int
    case_count: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class OrjsonFloatLayoutTestCase:
    """A float whose orjson text depends on the orjson version the native emitter reproduces."""

    description: str
    value: float
    expected_text: str


@dataclass(frozen=True)
class CloseMatchesOracleTestCase:
    """Seeded words compared between the native port and `difflib.get_close_matches`."""

    description: str
    seed: int
    case_count: int
    count: int
    cutoff: float
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class CleandocOracleTestCase:
    """Seeded SQL bodies compared between the native port and `inspect.cleandoc`."""

    description: str
    seed: int
    case_count: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class CharacterClassOracleTestCase:
    """A code point range classified natively and by Python's `str` methods."""

    description: str
    first: int
    last: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()
