"""Snowflake adapter constants."""

BASE_TABLE_METADATA_TYPE: str = "BASE TABLE"
VIEW_RELATION_TYPE_TOKEN: str = "view"
EXTERNAL_BROWSER_AUTHENTICATOR: str = "externalbrowser"
MFA_AUTHENTICATOR: str = "username_password_mfa"
OAUTH_AUTHORIZATION_CODE_AUTHENTICATOR: str = "oauth_authorization_code"
SECONDARY_ROLES_ALL: str = "ALL"
SECONDARY_ROLES_NONE: str = "NONE"
NUMBER_TYPE_NAME: str = "NUMBER"
NORMALIZED_LTZ_INPUT_TYPE_NAME: str = "TIMESTAMPLTZ"
NORMALIZED_NTZ_INPUT_TYPE_NAMES: frozenset[str] = frozenset({"TIMESTAMP", "TIMESTAMPNTZ"})
NORMALIZED_TZ_INPUT_TYPE_NAME: str = "TIMESTAMPTZ"
STATUS_COLUMN_NAME: str = "status"
SUCCESS_STATUS_TOKENS: tuple[str, ...] = ("success", "created", "dropped")
TEXT_TYPE_NAMES: frozenset[str] = frozenset({"TEXT", "VARCHAR", "CHAR", "CHARACTER"})
TEXT_TYPE_NAME: str = "TEXT"
TRUE_METADATA_VALUE: str = "YES"
