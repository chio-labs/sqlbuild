"""Shared relation metadata limits."""

INSPECTION_DESCRIBED_NAME_LIMIT: int = 3
INSPECTION_IN_LIST_LIMIT: int = 50
METADATA_NAME_FILTER_LIMIT: int = 250
SHORTENED_LOGICAL_NAME_HASH_LENGTH: int = 8
STATEMENT_SEPARATOR: str = ";"
QUOTED_IDENTIFIER_MIN_LENGTH: int = 2
DOUBLE_QUOTE: str = '"'
IDENTIFIER_QUOTE_PAIRS: frozenset[tuple[str, str]] = frozenset({("`", "`"), ("[", "]")})
RELATION_COLUMNS_LOOKUP: str = "columns"
RELATION_EXISTS_LOOKUP: str = "exists"
BACKTICK: str = "`"
