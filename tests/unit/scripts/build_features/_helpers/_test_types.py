from dataclasses import dataclass

from scripts.build_features.models import ResolvedCrate


@dataclass(frozen=True)
class ParseTreeTestCase:
    description: str
    output: str
    expected_crates: dict[ResolvedCrate, frozenset[str]]
