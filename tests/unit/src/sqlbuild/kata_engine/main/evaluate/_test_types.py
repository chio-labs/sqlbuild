"""Test cases for kata evaluation."""

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.kata_engine.models import KataConfig


@dataclass(frozen=True)
class KataEvaluationTestCase:
    description: str
    model_name: str
    relative_path: str
    sql: str
    config_values: dict[str, object]
    select: tuple[str, ...]
    expected_codes: tuple[str, ...]
    kata_config: KataConfig = field(default_factory=KataConfig)
    references: tuple[CompileSqlReference, ...] = ()
    authored_sql: str | None = None
    enum_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class KataBehaviorTestCase:
    description: str
    expected_fault_count: int = 0
    expected_cache_hits: int = 0
    expected_cache_misses: int = 0
    expected_error_pattern: str = ""


@dataclass(frozen=True)
class JoinRuleTestCase:
    description: str
    sql: str
    select: tuple[str, ...]
    expected_codes: tuple[str, ...]
    expected_remediations: tuple[str, ...] = ()
    kata_config: KataConfig = field(default_factory=KataConfig)
