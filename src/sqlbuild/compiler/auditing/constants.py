"""Stable constants for audit rendering."""

BUILT_IN_AUDIT_NAMES: frozenset[str] = frozenset(
    {"accepted_values", "not_null", "relationships", "unique"}
)
BUILT_IN_AUDIT_SHADOW_CODE: str = "P003"
MEASUREMENT_THRESHOLD_WARN_KEY: str = "warn"
MEASUREMENT_THRESHOLD_ERROR_KEY: str = "error"
MEASUREMENT_THRESHOLDS_HEADER_KEY: str = "thresholds"
MEASUREMENT_MINIMUM_SAMPLES_HEADER_KEY: str = "minimum_samples"
MEASUREMENT_OUTSIDE_BOUND_VALUE_COUNT: int = 2
SCHEMA_AUDIT_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "severity",
        "run_scope",
        "always_run",
        "thresholds",
        "minimum_samples",
        "evidence_limit",
    }
)
