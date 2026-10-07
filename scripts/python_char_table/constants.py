"""Paths and limits of the native Python character table generator."""

from pathlib import Path

TABLE_DIRECTORY: Path = (
    Path(__file__).resolve().parents[2]
    / "crates"
    / "sqlbuild-core"
    / "src"
    / "text"
    / "alnum_ranges"
)
TABLE_FILE_PREFIX: str = "unicode_"
TABLE_FILE_SUFFIX: str = ".in"
MAX_CODE_POINT: int = 0x10FFFF
