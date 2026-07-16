"""Generic CLI execution header formatting."""

from __future__ import annotations


def format_execution_header(*, command: str, target: str | None, concurrency: int) -> str:
    """Format command and execution context for a progress header."""

    parts: list[str] = [command]
    context_parts: list[str] = []
    if target is not None:
        context_parts.append(f"target: {target}")
    context_parts.append(f"concurrency: {concurrency}")
    if context_parts:
        parts.append(f"  ({', '.join(context_parts)})")
    return "".join(parts)
