"""Paths and limits of the native Python character table generator."""

from pathlib import Path

TABLE_PATH: Path = (
    Path(__file__).resolve().parents[2]
    / "crates"
    / "sqlbuild-core"
    / "src"
    / "text"
    / "_helpers"
    / "alnum_ranges.rs"
)
MAX_CODE_POINT: int = 0x10FFFF
