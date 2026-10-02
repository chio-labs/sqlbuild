"""Rules public errors."""


class RulesError(RuntimeError):
    """Raised for invalid compiler rules or execution."""


class RuleUsageError(RulesError):
    """Raised when a rule or rule test uses the public API incorrectly."""


class NonHermeticRuleError(RulesError):
    """Raised when a custom rule observes state the Rules cache cannot track."""


class RuleAssertionError(RulesError):
    """Raised when a custom-rule harness case produces an unexpected result."""


class FactDigestError(RulesError):
    """Raised when a recorded custom-rule fact cannot be recomputed or encoded deterministically."""


class OpaqueModuleStateError(RulesError):
    """Raised when custom-rule module state holds a value whose mutations cannot be observed."""
