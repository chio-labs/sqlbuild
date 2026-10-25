"""PostgreSQL adapter constants."""

TABLE_FUNCTION_RETURN_TYPE: str = "TABLE"
ROW_COUNT_RELATION_KINDS: frozenset[str] = frozenset({"r", "m"})
TRANSACTION_OPEN_STATUS: str = "INTRANS"
TEMPORARY_TEST_FUNCTIONS_KEY: str = "temporary_test_functions"
