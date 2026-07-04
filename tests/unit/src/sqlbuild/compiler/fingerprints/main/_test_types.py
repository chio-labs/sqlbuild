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


@dataclass(frozen=True)
class WriteFingerprintRetryTestCase:
    description: str
    failing_create_attempts: int
    error_message: str
    expected_create_attempts: int
    expected_insert_count: int
    expected_sleep_count: int


@dataclass(frozen=True)
class WriteFingerprintRetryExhaustionTestCase:
    description: str
    error_message: str
    expected_create_attempts: int
    expected_insert_count: int
    expected_error_fragment: str
