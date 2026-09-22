"""Fresh-process compile performance guard errors."""


class CgroupMemoryLimitError(RuntimeError):
    """Raised when a required compile memory limit is not active."""


class CompileBenchmarkFixtureError(RuntimeError):
    """Raised when a generated workload no longer satisfies its benchmark contract."""
