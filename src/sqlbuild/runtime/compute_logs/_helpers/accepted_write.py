"""Accepted write length normalization."""


def accepted_write_count(*, result: object, offered_count: int) -> int:
    """Normalize standard partial and None write results to an accepted prefix length."""

    if result is None:
        return offered_count
    if not isinstance(result, int):
        return 0
    return max(0, min(result, offered_count))
