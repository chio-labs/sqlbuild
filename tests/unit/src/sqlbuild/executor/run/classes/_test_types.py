from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeWatermarkResolverTestCase:
    description: str
    expected_query_count: int


@dataclass(frozen=True)
class FingerprintSetupTestCase:
    description: str
    first_writer_finishes: bool
    expected_requests: tuple[bool, bool]
