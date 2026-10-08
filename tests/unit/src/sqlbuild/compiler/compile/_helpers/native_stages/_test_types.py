from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import DynamicColumnContractProof, ModelSqlAnalysis
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


@dataclass(frozen=True)
class DynamicColumnContractDispatchTestCase:
    description: str
    sql_analysis: ModelSqlAnalysis | None
    dialect: str
    families: tuple[SchemaDynamicColumnFamily, ...]
    expected_proof: DynamicColumnContractProof | None
