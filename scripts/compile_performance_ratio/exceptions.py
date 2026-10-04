"""Same-runner compile performance comparison errors."""


class CompileComparisonError(RuntimeError):
    """Raised when a compared build fails to compile the benchmark project."""


class BenchmarkEditError(RuntimeError):
    """Raised when a benchmark project has no model query the one-model edit can change."""
