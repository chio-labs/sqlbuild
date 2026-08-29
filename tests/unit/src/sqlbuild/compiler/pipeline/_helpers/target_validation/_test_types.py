from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation


@dataclass(frozen=True)
class ValidateProjectTargetsTestCase:
    description: str
    adapter_name: str
    target: CompiledRelationLocation
    expected_error_fragment: str


@dataclass(frozen=True)
class ValidateManagedWriteSchemaTestCase:
    description: str
    adapter: BaseAdapter
    target_schema: str | None
    effective_connection: dict[str, object]
    expected_error_fragment: str | None
