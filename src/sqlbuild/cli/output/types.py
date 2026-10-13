"""Type-layer declarations for CLI output."""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.models import CompilerDiagnostic

type WrittenTargetDiagnostic = CompilerDiagnostic


class IntegrationOutputKind(StrEnum):
    """Kind of integration-facing result enrichment."""

    ASSET = "asset"
    CHECK = "check"
