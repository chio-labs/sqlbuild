"""Paths and limits of the native Python character table generator."""

from pathlib import Path

TABLE_ROOT: Path = Path(__file__).resolve().parents[2] / "crates" / "sqlbuild-core" / "src" / "text"
TABLE_FILE_PREFIX: str = "unicode_"
TABLE_FILE_SUFFIX: str = ".in"
MAX_CODE_POINT: int = 0x10FFFF
TABLE_METHODS: tuple[str, ...] = ("isalnum", "isalpha", "isdecimal")
MAPPING_METHODS: tuple[str, ...] = ("casefold", "upper")
IGNORECASE_KEY_TABLE: str = "re_ignorecase_keys"
SURROGATE_RANGE: range = range(0xD800, 0xE000)
