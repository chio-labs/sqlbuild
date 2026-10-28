"""Parameterized user-code finder test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FinderSpecTestCase:
    """One module to import, whether an earlier path entry shadows it, and the expected loader."""

    description: str
    module_name: str
    earlier_entries: tuple[str, ...]
    expected_source_only: bool
