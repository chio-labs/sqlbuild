"""Type-layer declarations for CLI output."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.models import CompilerDiagnostic

type WrittenTargetDiagnostic = CompilerDiagnostic
