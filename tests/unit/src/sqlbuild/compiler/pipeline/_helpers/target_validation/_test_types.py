from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledRelationLocation


@dataclass(frozen=True)
class ValidateProjectTargetsTestCase:
    description: str
    adapter_name: str
    target: CompiledRelationLocation
    expected_error_fragment: str
