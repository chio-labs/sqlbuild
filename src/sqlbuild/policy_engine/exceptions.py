"""Policy public errors."""


class PolicyError(RuntimeError):
    """Raised for invalid project policy or execution."""


class PolicyRuleUsageError(PolicyError):
    """Raised when a policy rule or rule test uses the public API incorrectly."""


class PolicyRuleAssertionError(PolicyError):
    """Raised when a custom-rule harness case produces an unexpected result."""
