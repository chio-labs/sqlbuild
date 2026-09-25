from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.types import MigrationTransfer


@dataclass(frozen=True)
class AdapterDurableCloneTestCase:
    description: str
    adapter: StrictAdapter
    source: str
    target: str
    expected_statements: tuple[str, ...]
    expected_supports_durable_clone: bool


@dataclass(frozen=True)
class AdapterCloneModeTestCase:
    description: str
    adapter: StrictAdapter
    source: str
    target: str
    hard_copy: bool
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class AdapterEligibleMaxCursorSqlTestCase:
    description: str
    adapter: StrictAdapter
    cursor_column: str
    maximum_allowed: str
    is_date: bool
    expected_sql: str


@dataclass(frozen=True)
class AdapterManagedWriteSchemaCapabilityTestCase:
    description: str
    adapter: BaseAdapter
    expected_allows_implicit_schema: bool


@dataclass(frozen=True)
class RowDiffSampleSqlTestCase:
    description: str
    adapter: BaseAdapter
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class AdapterRelationAgeMetadataCapabilityTestCase:
    description: str
    adapter: StrictAdapter
    expected_supported: bool


@dataclass(frozen=True)
class AdapterMigrationStageTestCase:
    description: str
    adapter: BaseAdapter
    origin_is_transient: bool
    stage_is_transient: bool | None
    expected_transfer: MigrationTransfer
    expected_statements: tuple[str, ...]
    expected_fallback_statements: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterTransactionalDdlTestCase:
    description: str
    adapter: BaseAdapter
    expected_transactional: bool
