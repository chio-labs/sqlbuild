"""Test cases for policy evaluation."""

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.policy_engine.models import PolicyConfig


@dataclass(frozen=True)
class PolicyEvaluationTestCase:
    description: str
    model_name: str
    relative_path: str
    sql: str
    config_values: dict[str, object]
    select: tuple[str, ...]
    expected_codes: tuple[str, ...]
    policy_config: PolicyConfig = field(default_factory=PolicyConfig)
    references: tuple[CompileSqlReference, ...] = ()
    authored_sql: str | None = None
    enum_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyBehaviorTestCase:
    description: str
    expected_fault_count: int = 0
    expected_cache_hits: int = 0
    expected_cache_misses: int = 0
    expected_error_pattern: str = ""
