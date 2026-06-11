from dataclasses import dataclass

from sqlbuild.compiler.fingerprints.models import Fingerprint


@dataclass(frozen=True)
class WriteAndReadTestCase:
    description: str
    database: str | None
    schema: str
    fingerprints: tuple[Fingerprint, ...]
    expected_node_names: tuple[str, ...]
    expected_latest_definition_hashes: dict[str, str]
    expected_latest_target_names: dict[str, str | None]
    expected_metadata_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadNonExistentTableTestCase:
    description: str
    database: str | None
    schema: str
    expected_node_count: int


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
    expected_latest_definition_hash: str
    expected_latest_definition: str


@dataclass(frozen=True)
class InvalidDefinitionStorageTestCase:
    description: str
    schema: str
    node_name: str
    raw_definition_storage: str
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class OldFingerprintSchemaTestCase:
    description: str
    schema: str
    expected_error_fragments: tuple[str, ...]
