"""Native project assembly request kinds and deferral record site."""

PROJECT_ASSEMBLY_DEFERRAL_SITE: str = "project_assembly"
TEXT_VARIABLE: str = "text"
BOOLEAN_VARIABLE: str = "bool"
NONE_VARIABLE: str = "none"
UNSUPPORTED_VARIABLE: str = "unsupported"
TRUE_TEXT: str = "1"
FALSE_TEXT: str = "0"
NATIVE_INT_MIN: int = -(2**63)
NATIVE_INT_MAX: int = 2**63 - 1
ENVIRONMENT_READ: str = "env"
ENVIRONMENT_NAME_PATTERN: str = r"ENV:([^\s(),'\"}]+)"
