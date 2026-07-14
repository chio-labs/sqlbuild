from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualPhysicalSchemaPreflightTestCase:
    description: str
    expected_schema: str
    expected_model_names: tuple[str, ...]
