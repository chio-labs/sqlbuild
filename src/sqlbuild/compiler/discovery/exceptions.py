"""Expected discovery-stage exception types."""


class DiscoveryError(ValueError):
    """Base error for expected discovery failures."""


class ProjectConfigError(DiscoveryError):
    """Raised when shared or local project config files are invalid."""


class ModelSqlParseError(DiscoveryError):
    """Raised when an authored SQL model file has an invalid shape."""


class SqlTestParseError(DiscoveryError):
    """Raised when an authored SQL-native test file has an invalid shape."""


class SqlAuditParseError(DiscoveryError):
    """Raised when an authored SQL audit file has an invalid shape."""
