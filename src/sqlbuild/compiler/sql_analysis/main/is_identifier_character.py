"""SQL identifier character classification entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import is_identifier_character_impl


def is_identifier_character(character: str) -> bool:
    """Return whether a character can continue an SQL identifier."""

    return is_identifier_character_impl(character)
