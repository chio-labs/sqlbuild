"""Stable constants for type annotation convention checks."""

PYTHON_FILE_SUFFIX: str = ".py"
METHOD_RECEIVER_PARAMETER_NAMES: frozenset[str] = frozenset({"self", "cls"})
DISCARDED_LOCAL_NAME: str = "_"
EXEMPT_MODULE_VARIABLE_NAMES: frozenset[str] = frozenset(
    {"__all__", "__match_args__", "__slots__", "__version__"}
)
EXEMPT_CLASS_ATTRIBUTE_NAMES: frozenset[str] = frozenset(
    {"__match_args__", "__slots__", "__test__"}
)
ENUM_BASE_CLASS_NAMES: frozenset[str] = frozenset({"Enum", "StrEnum"})
