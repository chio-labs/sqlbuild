"""Rules public errors."""


class RulesError(RuntimeError):
    """Raised for invalid compiler rules or execution."""


class RulesConfigError(RulesError):
    """Raised when rules configuration breaks a project policy; help shows the setting to change."""

    def __init__(self, message: str, *, help: str) -> None:
        super().__init__(message)
        self.message = message
        self.help = help


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


class HostCancelledError(RulesError):
    """Raised in a custom-rule host that stops because another host already failed."""
