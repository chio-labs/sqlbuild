from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionReturnContractIdentityTestCase:
    description: str
    original_type: str
    changed_type: str
    expected_changed: bool


@dataclass(frozen=True)
class FunctionUpstreamIdentityTestCase:
    description: str
    original_query: str
    changed_query: str
    expected_changed: bool


@dataclass(frozen=True)
class VersionIdentityConfigTestCase:
    description: str
    config_key: str
    expected_in_identity: bool


@dataclass(frozen=True)
class CursorRoleIdentityTestCase:
    description: str
    original_config: dict[str, object]
    changed_config: dict[str, object]
    expected_equal: bool


@dataclass(frozen=True)
class HookIdentityTestCase:
    description: str
    original_hooks: dict[str, object]
    changed_hooks: dict[str, object]
    expected_changed: bool


@dataclass(frozen=True)
class HookIdentityPayloadTestCase:
    description: str
    hooks: dict[str, object]
    expected_fragments: tuple[str, ...]
    forbidden_fragments: tuple[str, ...]
