"""Rules public errors."""


class RulesError(RuntimeError):
    """Raised for invalid compiler rules or execution."""


class RuleUsageError(RulesError):
    """Raised when a rule or rule test uses the public API incorrectly."""


class RuleAssertionError(RulesError):
    """Raised when a custom-rule harness case produces an unexpected result."""
