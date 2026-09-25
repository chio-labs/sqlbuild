"""One actionable semantic-check notice for human and machine commands."""

from sqlbuild.compiler.compile.main.semantic_coverage import get_semantic_coverage
from sqlbuild.compiler.compile.models import CompiledProject

_TYPE_COVERAGE_REASON: str = "type checking awaits dialect coercion support"


def semantic_coverage_notice(project: CompiledProject) -> str | None:
    """Summarize partial checks without increasing the diagnostic warning count."""
    reasons: dict[str, tuple[str, ...]] = get_semantic_coverage(project)
    if not reasons:
        return None
    sources: set[str] = set()
    for values in reasons.values():
        sources.update(
            reason.removeprefix("open source: ")
            for reason in values
            if reason.startswith("open source: ")
        )
    open_sources: list[str] = sorted(sources)
    text: str = f"Semantic checks were partial for {len(reasons)} models."
    if any(_TYPE_COVERAGE_REASON in values for values in reasons.values()):
        text += " Type checking awaits dialect coercion support."
    if open_sources:
        text += (
            f" Open sources: {', '.join(open_sources)}. "
            "Run `sqb contract generate --from <target> "
            f"--select source:{open_sources[0]} --write` or add `contract enforced`."
        )
    return text
