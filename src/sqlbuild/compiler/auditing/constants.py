"""Stable constants for audit rendering."""

BUILT_IN_AUDIT_NAMES: frozenset[str] = frozenset(
    {"accepted_values", "not_null", "relationships", "unique"}
)
BUILT_IN_AUDIT_SHADOW_CODE: str = "P003"
