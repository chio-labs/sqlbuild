"""Effective target identifier semantics for native schema validation."""

_SNOWFLAKE: str = "snowflake"
_PARAMETER: str = "QUOTED_IDENTIFIERS_IGNORE_CASE"


def ignores_quoted_case(*, connection: dict[str, object], dialect: str | None) -> bool:
    """Read only an explicitly enabled setting from the resolved connection."""
    if dialect != _SNOWFLAKE:
        return False
    parameters: object = connection.get("session_parameters")
    if not isinstance(parameters, dict):
        return False
    return any(
        str(key).upper() == _PARAMETER and value is True for key, value in parameters.items()
    )
