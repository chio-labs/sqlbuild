"""Kata public errors."""


class KataError(RuntimeError):
    """Raised for invalid kata policy or execution."""


class KataRuleUsageError(KataError):
    """Raised when a kata rule or rule test uses the public API incorrectly."""


class KataRuleAssertionError(KataError):
    """Raised when a custom-rule harness case produces an unexpected result."""
