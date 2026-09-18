"""Constants for diff execution."""

ROW_DIFF_ABSOLUTE_TOLERANCE_KEY: str = "absolute"
ROW_DIFF_RELATIVE_TOLERANCE_KEY: str = "relative"
DIFF_INPUT_KIND_MODEL: str = "model"
DIFF_INPUT_KIND_QUERY: str = "query"
ROW_DIFF_KEY_ERROR_PREFIX: str = "row diff "
ROW_DIFF_KEY_ERROR_FRAGMENT: str = " unique_key values"
ROW_DIFF_TOLERANCE_KEYS: frozenset[str] = frozenset(
    (ROW_DIFF_ABSOLUTE_TOLERANCE_KEY, ROW_DIFF_RELATIVE_TOLERANCE_KEY)
)
