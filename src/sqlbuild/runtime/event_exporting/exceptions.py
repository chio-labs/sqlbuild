"""Event exporter declaration and runtime errors."""


class EventExporterError(ValueError):
    """Base event exporter error."""


class EventExporterInputError(EventExporterError):
    """Raised when an exporter declaration or runtime setting is invalid."""


class EventExporterStateError(EventExporterError):
    """Raised when exporter runtime ownership is used inconsistently."""
