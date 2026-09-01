from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeWatermarkResolverTestCase:
    description: str
    expected_query_count: int
