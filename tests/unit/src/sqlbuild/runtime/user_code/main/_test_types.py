"""Parameterized user-code loading test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StaleBytecodeTestCase:
    """One project file edited without changing its size or mtime after bytecode was cached."""

    description: str
    edited_file: str
    expected_value: str
