from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


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


@dataclass(frozen=True)
class ValidateNamedTargetSchemaTestCase:
    description: str
    adapter: BaseAdapter
    project_config: ProjectConfig
    local_config: LocalConfig
    selected_target: str | None
    expected_error_fragment: str | None
