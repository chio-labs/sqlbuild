from dataclasses import dataclass

from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord


@dataclass(frozen=True)
class SourceFreshnessWriteAndReadTestCase:
    description: str
    database: str | None
    schema: str
    records: tuple[SourceFreshnessRecord, ...]
    expected_identities: tuple[SourceFreshnessIdentity, ...]
    expected_latest_hashes: dict[SourceFreshnessIdentity, str]
    expected_latest_target_names: dict[SourceFreshnessIdentity, str | None]


@dataclass(frozen=True)
class SourceFreshnessReadNonExistentTableTestCase:
    description: str
    database: str | None
    schema: str
    expected_record_count: int


@dataclass(frozen=True)
class SourceFreshnessWriteCreatesTableTestCase:
    description: str
    database: str | None
    schema: str
    record: SourceFreshnessRecord
    expected_table_exists: bool


@dataclass(frozen=True)
class SourceFreshnessLatestResolutionTestCase:
    description: str
    database: str | None
    schema: str
    records: tuple[SourceFreshnessRecord, ...]
    identity: SourceFreshnessIdentity
    expected_latest_run_id: str
    expected_latest_data_version_hash: str
    expected_latest_data_version: str | None


@dataclass(frozen=True)
class SourceFreshnessRoundTripTestCase:
    description: str
    database: str | None
    schema: str
    record: SourceFreshnessRecord
    expected_data_version: str | None
    expected_data_version_hash: str
