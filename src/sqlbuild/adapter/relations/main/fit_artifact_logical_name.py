"""Generated relation name fitting entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.relations._helpers.identifier_fitting import fit_artifact_logical_name_impl


def fit_artifact_logical_name(
    *, logical_name: str, fixed_prefix: str, identifier_limit: int, artifact_label: str
) -> str:
    """Fit a readable logical component after a fixed prefix within an identifier limit."""

    return fit_artifact_logical_name_impl(
        logical_name=logical_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
        artifact_label=artifact_label,
    )
