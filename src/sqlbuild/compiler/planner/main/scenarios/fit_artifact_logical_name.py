"""Public SQLBuild-owned artifact name fitting entrypoint."""

from sqlbuild.compiler.planner._helpers.scenario.artifact_names import (
    fit_artifact_logical_name as _fit_artifact_logical_name,
)


def fit_artifact_logical_name(
    *, logical_name: str, fixed_prefix: str, identifier_limit: int, artifact_label: str
) -> str:
    """Fit one readable artifact component within an adapter identifier limit."""

    return _fit_artifact_logical_name(
        logical_name=logical_name,
        fixed_prefix=fixed_prefix,
        identifier_limit=identifier_limit,
        artifact_label=artifact_label,
    )
