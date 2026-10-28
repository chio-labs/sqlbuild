"""DuckShop house rule that keeps the edge-case area selectable on its own."""

import re

from sqlbuild.rules import Finding, Model, RuleContext, rule

EDGE_FOLDER = "edge_cases"
EDGE_TAG = "edge_case"
_HEADER_TAGS = re.compile(r"^[ \t]*tags\s*\[([^\]]*)\]", re.MULTILINE)


def _header_tags(sql: str) -> tuple[set[str], int]:
    header_end = sql.find(");")
    match = _HEADER_TAGS.search(sql, 0, header_end if header_end >= 0 else len(sql))
    if match is None:
        return set(), 1
    tags = {tag.strip().strip("\"'") for tag in match.group(1).split(",") if tag.strip()}
    return tags, sql[: match.start()].count("\n") + 1


@rule(
    code="XSQBRDUCK002",
    message="Models in an edge_cases folder, and only those, must declare the edge_case tag",
    remediation=(
        "Add `tags [edge_case]` to the header of every model under models/<layer>/edge_cases/, "
        "and move a model that declares the tag into that folder, so benchmark and core runs can "
        "exclude the edge-case area with --exclude tag:edge_case."
    ),
)
def edge_area_is_tagged(*, model: Model, ctx: RuleContext) -> list[Finding]:
    parts = ctx.project.tree.relative_parts(path=model.path, under="models")
    in_area = EDGE_FOLDER in parts
    tags, line = _header_tags(ctx.sql.for_model(model).authored.source)
    if in_area == (EDGE_TAG in tags):
        return []
    return [ctx.finding(subject=model, line=line)]
