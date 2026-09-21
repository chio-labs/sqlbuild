"""Fresh-process compile performance guard errors."""


class CgroupMemoryLimitError(RuntimeError):
    """Raised when a required compile memory limit is not active."""
