from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledRelationTarget


@dataclass(frozen=True)
class ValidateProjectTargetsTestCase:
    description: str
    adapter_name: str
    target: CompiledRelationTarget
    expected_error_fragment: str
