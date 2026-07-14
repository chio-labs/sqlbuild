"""SQL identifier start classification entrypoint."""

from sqlbuild.compiler.sql_analysis.helpers.scanning import is_identifier_start_impl


def is_identifier_start(character: str) -> bool:
    """Return whether a character can begin an SQL identifier."""

    return is_identifier_start_impl(character)
