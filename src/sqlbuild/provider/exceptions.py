"""Provider exceptions."""


class ProviderInputError(ValueError):
    """Raised when a provider definition is invalid."""


class ProviderLookupError(LookupError):
    """Raised when a provider cannot be found at runtime."""


class ProviderSetupError(RuntimeError):
    """Raised when provider setup fails."""


class ProviderTeardownError(RuntimeError):
    """Raised when provider teardown fails."""
