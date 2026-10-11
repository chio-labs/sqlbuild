"""A native dynamic pivot proof row as Python's proof, for hand-built model inputs only."""

from __future__ import annotations

from sqlbuild.compiler.analysis_session._helpers.session_rows import contract_proof
from sqlbuild.compiler.analysis_session.types import ProofRow
from sqlbuild.compiler.compile.models import DynamicColumnContractProof


def dynamic_contract_proof(row: ProofRow | None) -> DynamicColumnContractProof | None:
    """The proof, or None when the row is absent."""

    return contract_proof(row)
