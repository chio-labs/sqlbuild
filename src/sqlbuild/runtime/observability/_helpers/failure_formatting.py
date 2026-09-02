"""Safe bounded formatting for dispatcher health records."""

_FAILURE_TEXT_LIMIT: int = 512
_ERROR_MESSAGE_FALLBACK: str = "<unprintable subscriber exception>"
_ERROR_TYPE_FALLBACK: str = "<unknown exception type>"
_SUBSCRIBER_FALLBACK: str = "<unknown subscriber>"


def _safe_text(*, value: object, fallback: str) -> str:
    try:
        return str(value)[:_FAILURE_TEXT_LIMIT]
    except Exception:
        return fallback


def _safe_subscriber_name(*, subscriber: object) -> str:
    """Return a bounded subscriber name without invoking unsafe formatting."""

    try:
        name: object = getattr(subscriber, "__qualname__", type(subscriber).__qualname__)
    except Exception:
        return _SUBSCRIBER_FALLBACK
    return _safe_text(value=name, fallback=_SUBSCRIBER_FALLBACK)


def _safe_error_type(*, error: Exception) -> str:
    """Return a bounded exception type name with a static fallback."""

    try:
        name: object = type(error).__qualname__
    except Exception:
        return _ERROR_TYPE_FALLBACK
    return _safe_text(value=name, fallback=_ERROR_TYPE_FALLBACK)


def _safe_error_message(*, error: Exception) -> str:
    """Return a bounded exception message with a static fallback."""

    return _safe_text(value=error, fallback=_ERROR_MESSAGE_FALLBACK)
