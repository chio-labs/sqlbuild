"""Skipped type-proof rules note entrypoint."""


def format_skipped_type_proof_rules(*, codes: tuple[str, ...]) -> str | None:
    """Describe type-proof rules skipped because SQL analysis is disabled, if any."""

    if not codes:
        return None
    return f"skipped type-proof rules ({', '.join(codes)}) because SQL analysis is disabled"
