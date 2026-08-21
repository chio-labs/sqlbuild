"""Map offsets in rendered SQL back onto the authored text that produced them."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import ExpansionSpan, MappedOffset


def map_output_offset(*, offset: int, spans: tuple[ExpansionSpan, ...]) -> MappedOffset:
    """Resolve one rendered offset through a single expansion pass."""

    mapped: int = offset
    span: ExpansionSpan
    for span in spans:
        if offset < span.output_start:
            break
        if offset < span.output_end:
            return MappedOffset(offset=span.source_start, generated=True)
        mapped += (span.source_end - span.source_start) - (span.output_end - span.output_start)
    return MappedOffset(offset=mapped, generated=False)


def map_through_passes(
    *, offset: int, passes: tuple[tuple[ExpansionSpan, ...], ...]
) -> MappedOffset:
    """Resolve one rendered offset back through every expansion pass in order."""

    current: int = offset
    generated: bool = False
    spans: tuple[ExpansionSpan, ...]
    for spans in reversed(passes):
        resolved: MappedOffset = map_output_offset(offset=current, spans=spans)
        current = resolved.offset
        generated = generated or resolved.generated
    return MappedOffset(offset=current, generated=generated)
