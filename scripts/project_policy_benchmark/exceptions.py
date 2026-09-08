"""Project Policy benchmark failures."""


class PolicyBenchmarkError(RuntimeError):
    """Raised when a benchmark process violates its expected contract."""
