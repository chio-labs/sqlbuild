from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledRelationDestination


@dataclass(frozen=True)
class ValidateProjectTargetsTestCase:
    description: str
    adapter_name: str
    target: CompiledRelationDestination
    expected_error_fragment: str
