"""Snowflake adapter constants."""

BASE_TABLE_METADATA_TYPE: str = "BASE TABLE"
EXTERNAL_BROWSER_AUTHENTICATOR: str = "externalbrowser"
MFA_AUTHENTICATOR: str = "username_password_mfa"
NUMBER_TYPE_NAME: str = "NUMBER"
NORMALIZED_LTZ_INPUT_TYPE_NAME: str = "TIMESTAMPLTZ"
NORMALIZED_NTZ_INPUT_TYPE_NAMES: frozenset[str] = frozenset({"TIMESTAMP", "TIMESTAMPNTZ"})
NORMALIZED_TZ_INPUT_TYPE_NAME: str = "TIMESTAMPTZ"
STATUS_COLUMN_NAME: str = "status"
SUCCESS_STATUS_TOKENS: tuple[str, ...] = ("success", "created", "dropped")
TEXT_TYPE_NAMES: frozenset[str] = frozenset({"TEXT", "VARCHAR", "CHAR", "CHARACTER"})
TEXT_TYPE_NAME: str = "TEXT"
TRUE_METADATA_VALUE: str = "YES"
