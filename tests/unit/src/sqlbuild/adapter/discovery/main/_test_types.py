from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectAdapterDiscoveryTestCase:
    description: str
    files: dict[str, str]
    expected_adapter_names: tuple[str, ...] = field(default_factory=tuple)
    reserved_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ProjectAdapterDiscoveryErrorTestCase:
    description: str
    files: dict[str, str]
    expected_error_fragment: str
    reserved_names: frozenset[str] = frozenset()
