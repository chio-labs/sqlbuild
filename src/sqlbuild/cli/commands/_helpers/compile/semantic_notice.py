"""One actionable semantic-check notice for human and machine commands."""

from sqlbuild.compiler.compile.main.semantic_coverage import get_semantic_coverage
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType

_DISPLAY_LIMIT: int = 10
_ACTIONS: dict[str, str] = {
    "some output types are unknown": "declare output types, then run `sqb compile --no-cache`",
    "output shape could not be inferred": "declare the output schema; run `sqb compile --no-cache`",
    "unresolved star over open inputs": (
        "declare complete input contracts, then run `sqb compile --no-cache`"
    ),
    "SQL analysis disabled": "enable sql_analysis, then run `sqb compile --no-cache`",
    "type checking awaits dialect coercion support": (
        "use a supported dialect for type checks; run `sqb compile --json` to inspect coverage"
    ),
}


def selected_semantic_coverage(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey] | None
) -> dict[str, tuple[str, ...]]:
    """Report coverage for the compile selection rather than unanalyzed sibling models."""
    reasons: dict[str, tuple[str, ...]] = get_semantic_coverage(project)
    if selected_keys is None:
        return reasons
    names: set[str] = {
        key.name for key in selected_keys if key.resource_type == CompiledResourceType.MODEL
    }
    return {name: values for name, values in reasons.items() if name in names}


def semantic_coverage_notice(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey] | None = None
) -> str | None:
    """Summarize partial checks without increasing the diagnostic warning count."""
    reasons: dict[str, tuple[str, ...]] = selected_semantic_coverage(
        project=project, selected_keys=selected_keys
    )
    if not reasons:
        return None
    groups: dict[str, list[str]] = {}
    for model, values in sorted(reasons.items()):
        for reason in values:
            groups.setdefault(reason, []).append(model)
    lines: list[str] = [f"Semantic checks were partial for {len(reasons)} models:"]
    for reason, models in sorted(groups.items())[:10]:
        suffix: str = (
            f", and {len(models) - _DISPLAY_LIMIT} more" if len(models) > _DISPLAY_LIMIT else ""
        )
        detail: str = reason.replace("open source: ", "reads open source ").replace(
            "open input: ", "reads open input "
        )
        action: str = _ACTIONS.get(
            reason, "declare the input shape, then run `sqb compile --no-cache`"
        )
        if reason.startswith("open source: "):
            source: str = reason.removeprefix("open source: ")
            action = (
                "run `sqb contract generate --from <target> "
                f"--select source:{source} --write` and enforce the complete source contract"
            )
        elif reason.startswith("depends on invalid model "):
            action = "fix the upstream error, then run `sqb compile --no-cache`"
        lines.append(f"  {', '.join(models[:10])}{suffix}: {detail}; {action}.")
    if len(groups) > _DISPLAY_LIMIT:
        lines.append(
            f"  and {len(groups) - 10} more reasons; "
            "run `sqb compile --json` for the full model/reason list."
        )
    return "\n".join(lines)
