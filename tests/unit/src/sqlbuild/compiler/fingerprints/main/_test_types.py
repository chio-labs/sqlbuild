from dataclasses import dataclass


@dataclass(frozen=True)
class ReadLatestFingerprintsTestCase:
    description: str
    rows: list[tuple[object, ...]]
    expected_model_name: str
    expected_version_hash: str
    expected_query_sql: str
    expected_metadata_json: str


@dataclass(frozen=True)
class ReadLatestFingerprintsErrorTestCase:
    description: str
    read_error: Exception
    expected_message_fragment: str


@dataclass(frozen=True)
class ReadLatestFingerprintsRendererTestCase:
    description: str
    expected_executed_sql: str


@dataclass(frozen=True)
class WriteFingerprintIndexTestCase:
    description: str
    expected_index_sql: str
    expected_insert_prefix: str
