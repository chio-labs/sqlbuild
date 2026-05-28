from dataclasses import dataclass

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


@dataclass(frozen=True)
class AdapterDurableCloneTestCase:
    description: str
    adapter: StrictAdapter
    source: str
    target: str
    expected_statements: tuple[str, ...]
    expected_supports_durable_clone: bool
