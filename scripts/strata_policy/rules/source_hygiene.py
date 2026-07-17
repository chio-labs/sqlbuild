"""Repository-specific source terminology and comment rules."""

from __future__ import annotations

from strata import Family, Fault, RuleContext, rule

from scripts.strata_policy.constants import (
    ALLOWED_COMMENT_PREFIXES,
    GLOBAL_REUSE_FORBIDDEN_TERMS,
    POLICY_EVALUATION_SCOPES,
    POLICY_IMPLEMENTATION_PATH_PREFIX,
    REUSE_FORBIDDEN_TERMS,
    REUSE_PATH_MARKERS,
    REUSE_TERM_ALLOWED_PATHS,
)


@rule(
    code="XSB045",
    family=Family.CUSTOM,
    slug="reuse-terminology",
    message="clone and reuse code must use unambiguous origin and destination terminology",
    remediation="Use origin, destination, and reuse_from; source means a SQLBuild source node.",
)
def reuse_terminology(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path.startswith(POLICY_IMPLEMENTATION_PATH_PREFIX):
        return []
    terms: tuple[str, ...] = GLOBAL_REUSE_FORBIDDEN_TERMS
    if any(marker in path for marker in REUSE_PATH_MARKERS):
        terms = (*terms, *REUSE_FORBIDDEN_TERMS)
    faults: list[Fault] = []
    line_number: int
    line: str
    for line_number, line in enumerate(ctx.text.source.splitlines(), start=1):
        term: str
        for term in terms:
            if term not in line or path in REUSE_TERM_ALLOWED_PATHS.get(term, frozenset()):
                continue
            faults.append(
                ctx.fault_for(
                    path=ctx.path,
                    line=line_number,
                    column=0,
                    message=f"clone/reuse code uses ambiguous term '{term}'",
                )
            )
    return faults


@rule(
    code="XSB056",
    family=Family.CUSTOM,
    slug="sqlbuild-comment-policy",
    message="runtime and tooling comments must be approved directives",
    remediation="Prefer clear names or docstrings; keep only recognized tool directives.",
)
def sqlbuild_comment_policy(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    return [
        ctx.fault_for(
            path=comment.path,
            line=comment.line,
            column=comment.column,
        )
        for comment in ctx.facts.comments()
        if not comment.text.strip().startswith(ALLOWED_COMMENT_PREFIXES)
    ]
