from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSchemaPreflightTestCase:
    description: str
    expected_schemas: tuple[tuple[str | None, str], ...]


@dataclass(frozen=True)
class RunnableGraphWidthTestCase:
    description: str
    expected_width: int


@dataclass(frozen=True)
class PipelineIdentityTestCase:
    description: str
    expected_invocation_id: str
    expected_run_id: str
