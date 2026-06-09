from dataclasses import dataclass

from sqlbuild.compiler.fingerprints.models import Fingerprint


@dataclass(frozen=True)
class WriteAndReadTestCase:
    description: str
    database: str | None
    schema: str
    fingerprints: tuple[Fingerprint, ...]
    expected_model_names: tuple[str, ...]
    expected_latest_query_hashes: dict[str, str]
    expected_latest_target_names: dict[str, str | None]


@dataclass(frozen=True)
class ReadNonExistentTableTestCase:
    description: str
    database: str | None
    schema: str
    expected_model_count: int


@dataclass(frozen=True)
class WriteCreatesTableTestCase:
    description: str
    database: str | None
    schema: str
    fingerprint: Fingerprint
    expected_table_exists: bool


@dataclass(frozen=True)
class LatestResolutionTestCase:
    description: str
    database: str | None
    schema: str
    fingerprints: tuple[Fingerprint, ...]
    expected_latest_run_id: str
    expected_latest_query_hash: str
    expected_latest_query_sql: str


@dataclass(frozen=True)
class InvalidQuerySqlStorageTestCase:
    description: str
    schema: str
    model_name: str
    raw_query_sql_storage: str
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class OldFingerprintSchemaTestCase:
    description: str
    schema: str
    expected_error_fragments: tuple[str, ...]
