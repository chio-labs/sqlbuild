"""Expected discovery-stage exception types."""

from __future__ import annotations


class DiscoveryError(ValueError):
    """Base error for expected discovery failures."""

    code: str = "D000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class ProjectConfigError(DiscoveryError):
    """Raised when shared or local project config files are invalid."""

    code: str = "D001"


class ModelSqlParseError(DiscoveryError):
    """Raised when an authored SQL model file has an invalid shape."""

    code: str = "D002"


class ModelHeaderSyntaxError(DiscoveryError):
    """Raised when a MODEL(...) SQLBuild header cannot be parsed."""

    code: str = "D002"


class SqlTestParseError(DiscoveryError):
    """Raised when an authored SQL-native test file has an invalid shape."""

    code: str = "D003"


class SqlAuditParseError(DiscoveryError):
    """Raised when an authored SQL audit file has an invalid shape."""

    code: str = "D004"


class SchemaParseError(DiscoveryError):
    """Raised when a schema.yml file has an invalid shape."""

    code: str = "D005"


class SourceParseError(DiscoveryError):
    """Raised when a sources/*.yml file has an invalid shape."""

    code: str = "D006"


class DiscoveryConflictError(DiscoveryError):
    """Raised when discovered project inputs conflict across files."""

    code: str = "D007"


class SeedDiscoveryError(DiscoveryError):
    """Raised when declared seed metadata does not match local seed files."""

    code: str = "D008"


class SqlScenarioParseError(DiscoveryError):
    """Raised when an authored SQL scenario file has an invalid shape."""

    code: str = "D009"


class LoaderDiscoveryError(DiscoveryError):
    """Raised when project source loaders cannot be discovered."""

    code: str = "D010"
