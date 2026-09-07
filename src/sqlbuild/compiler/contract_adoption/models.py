"""Contract adoption domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.contract_adoption.types import ContractFindingKind


@dataclass(frozen=True)
class ContractFinding:
    resource_type: CompiledResourceType
    resource_name: str
    kind: ContractFindingKind
    message: str
    column_name: str | None = None
    declared_type: str | None = None
    physical_type: str | None = None


@dataclass(frozen=True)
class ContractEvidence:
    resource_type: CompiledResourceType
    resource_name: str
    database: str | None
    schema: str | None
    relation: str
    declared_columns: tuple[ColumnInfo, ...]
    physical_columns: tuple[ColumnInfo, ...] | None
    source_path: Path | None
    findings: tuple[ContractFinding, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContractAdoptionResult:
    from_target: str
    evidence: tuple[ContractEvidence, ...]
    written_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def findings(self) -> tuple[ContractFinding, ...]:
        findings: list[ContractFinding] = []
        for item in self.evidence:
            findings.extend(item.findings)
        return tuple(findings)
