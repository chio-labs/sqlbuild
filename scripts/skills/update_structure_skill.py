"""Generate the SQLBuild structure boundary opencode skill."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from scripts.skills.models import RuleReference

generated_marker: str = "<!-- generated-by: make skills -->"
else_branch_key: str = "__else__"
skill_name: str = "sqlbuild-structure"
skill_description: str = (
    "Use when modifying SQLBuild Python package structure, imports, boundaries, main/ "
    "entry modules, helpers/, shared/, classes/, models.py, types.py, constants.py, "
    "exceptions.py, adapter/integration modules, or fixing make check structure convention "
    "violations SC001-SC068."
)
default_source_path: Path = Path("scripts/structure/structure_conventions/rules.py")
default_output_path: Path = Path.home() / ".config/opencode/skills/sqlbuild-structure/SKILL.md"


def main(argv: list[str] | None = None) -> int:
    """Generate and write the SQLBuild structure skill."""

    args: argparse.Namespace = _parse_args(argv)
    skill_markdown: str = build_skill_markdown(
        repo_root=args.repo_root,
        source_path=args.source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(skill_markdown, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def build_skill_markdown(*, repo_root: Path, source_path: Path) -> str:
    """Build the generated SQLBuild structure skill markdown."""

    absolute_source_path: Path = repo_root / source_path
    rule_references: tuple[RuleReference, ...] = extract_rule_references(
        source_path=absolute_source_path
    )
    rendered_rules: str = "\n".join(_render_rule_reference(rule) for rule in rule_references)
    return (
        _normalize_blank_lines(
            f"""---
name: {skill_name}
description: {skill_description}
compatibility: opencode
---

{generated_marker}

# SQLBuild Structure Boundaries

This skill captures SQLBuild's Python package boundary rules from `{source_path.as_posix()}`.
Load it before changing runtime or script structure, not after `make check` fails.

## Load Before

Use this before changing Python files under `src/sqlbuild/` or `scripts/`, especially when:

- moving code between packages
- adding imports across subpackages or domains
- creating or changing `main/`, `helpers/`, `shared/`, `classes/`, `models/`, `types/`,
  `constants/`, or `exceptions/`
- touching adapter or integration package boundaries
- fixing `make check` structure convention failures

## Most Missed Rules

- Do not import sibling package internals. Promote shared code to the parent `shared/` boundary.
- Treat `main/` as a focused entry boundary, not a place to reach casually into sibling internals.
- Keep `main/` public functions as ordered lists of named phases; extract cohesive stages
  into `helpers/` functions that return frozen result models instead of mutating arguments.
- Keep nested runtime packages role-oriented; avoid arbitrary buckets and put support code
  under `helpers/`.
- Keep `shared/` dependency-neutral; it must not import sibling package internals.
- Put structured runtime models in `models.py` or `models/`.
- Put type-layer declarations in `types.py` or `types/`.
- Put custom exceptions in `exceptions.py` or `exceptions/`, not under `helpers/`.
- Keep adapter and integration `client.py` files as focused single-class surfaces.

## Workflow

1. Identify the package boundary you are changing before editing imports or files.
2. Prefer moving shared behavior upward to `shared/` over importing sideways.
3. Prefer role files and explicit support boundaries over new feature buckets.
4. Run `make check` after the change and fix any `SC...` violations using this reference.

## Main Orchestrators And Phase Functions

- A `main/` public function is an orchestrator: it should read as an ordered list of named
  phase calls, not as an inline script with interleaved intermediate state.
- Name each extracted phase after the result it produces, such as `resolve_planner_scopes`
  or `detect_staleness`; do not create `_part_one`-style splits.
- Phase helpers accept explicit inputs and RETURN a named result model. Use frozen models
  over mutable threading so dataflow is visible at call sites.
- Main orchestrators consume phase results by assigning them to typed locals or returning
  them. Bare function calls are reserved for raise-or-pass validators (`validate_*`,
  `enforce_*`, `check_*`), callbacks and progress reporting (`on_*`, `report_*`),
  diagnostics (`log*`, `print`), and writers (`write_*`); these prefixes are contracts,
  so do not use them for real phases that produce values. Discard a genuine void effect
  explicitly with `_ = ...` instead of a bare call.
- Orchestrators may drive resources they own through method calls (connections, CLI
  reporters, local accumulators such as `results.append(...)`); phases themselves are
  functions and must hand results back as values, never by mutating shared objects.
- `SC063`, `SC064`, and `SC065` cap statements, distinct calls, and locals for every
  top-level function in main/ modules, private helpers included; private functions in
  main/ are small glue, so phase-sized logic belongs in `helpers/`. `SC066` rejects
  discarded phase function call results in all main/ top-level functions. `SC067` rejects
  helpers mutating their parameters (`self`/`cls` exempt) unless a deliberate builder is
  marked with `# sc: allow-param-mutation`. `SC068` requires frozen dataclass result
  models in `models.py`.

## Generated Rule Reference

{rendered_rules}
"""
        ).strip()
        + "\n"
    )


def extract_rule_references(*, source_path: Path) -> tuple[RuleReference, ...]:
    """Extract convention codes and messages from Violation(...) calls."""

    module: ast.Module = ast.parse(source_path.read_text(encoding="utf-8"))
    rules_by_key: dict[tuple[str, str], RuleReference] = {}
    for function_node in (node for node in ast.walk(module) if isinstance(node, ast.FunctionDef)):
        for rule_reference in _extract_function_rule_references(function_node):
            rules_by_key.setdefault(
                (rule_reference.code, rule_reference.message),
                rule_reference,
            )

    return tuple(sorted(rules_by_key.values(), key=lambda rule: (rule.code, rule.message)))


def _extract_function_rule_references(function_node: ast.FunctionDef) -> tuple[RuleReference, ...]:
    references: list[RuleReference] = []
    expression_names: dict[str, tuple[str, ...]] = {}
    conditional_expression_names: dict[str, dict[str, str]] = {}
    for node in ast.walk(function_node):
        expression_names, conditional_expression_names = _capture_string_assignment(
            node=node,
            expression_names=expression_names,
            conditional_expression_names=conditional_expression_names,
        )
        if not isinstance(node, ast.Call) or not _is_violation_call(node):
            continue
        codes: tuple[str, ...] = _keyword_string_options(
            node=node,
            keyword_name="code",
            expression_names=expression_names,
        )
        messages: tuple[str, ...] = _keyword_string_options(
            node=node,
            keyword_name="message",
            expression_names=expression_names,
        )
        paired_messages: dict[str, str] = _conditional_keyword_messages_by_code(
            node=node,
            keyword_name="message",
            conditional_expression_names=conditional_expression_names,
        )
        for code in codes:
            code_messages: tuple[str, ...] = (
                (paired_messages[code],) if code in paired_messages else messages
            )
            if code not in paired_messages and else_branch_key in paired_messages:
                code_messages = (paired_messages[else_branch_key],)
            for message in code_messages:
                references.append(RuleReference(code=code, message=_normalize_message(message)))
    return tuple(references)


def _capture_string_assignment(
    *,
    node: ast.AST,
    expression_names: dict[str, tuple[str, ...]],
    conditional_expression_names: dict[str, dict[str, str]],
) -> tuple[dict[str, tuple[str, ...]], dict[str, dict[str, str]]]:
    target_name: str | None = None
    value: ast.expr | None = None
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        target_name = node.target.id
        value = node.value
    elif (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        target_name = node.targets[0].id
        value = node.value

    if target_name is None or value is None:
        return expression_names, conditional_expression_names

    expression_options: tuple[str, ...] = _string_expression_options(value)
    if expression_options:
        expression_names[target_name] = expression_options
    conditional_options: dict[str, str] = _conditional_string_expression_options(value)
    if conditional_options:
        conditional_expression_names[target_name] = conditional_options
    return expression_names, conditional_expression_names


def _conditional_keyword_messages_by_code(
    *,
    node: ast.Call,
    keyword_name: str,
    conditional_expression_names: dict[str, dict[str, str]],
) -> dict[str, str]:
    for keyword in node.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Name):
            return conditional_expression_names.get(keyword.value.id, {})
    return {}


def _is_violation_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "Violation"


def _keyword_string_options(
    *, node: ast.Call, keyword_name: str, expression_names: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    for keyword in node.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Name):
            return expression_names.get(keyword.value.id, ())
        return _string_expression_options(keyword.value)
    return ()


def _string_expression_options(node: ast.expr) -> tuple[str, ...]:
    if isinstance(node, ast.IfExp):
        return (*_string_expression_options(node.body), *_string_expression_options(node.orelse))
    expression_text: str | None = _string_expression_text(node)
    if expression_text is None:
        return ()
    return (expression_text,)


def _conditional_string_expression_options(node: ast.expr) -> dict[str, str]:
    if not isinstance(node, ast.IfExp):
        return {}
    condition_code: str | None = _code_equality_constant(node.test)
    body_text: str | None = _string_expression_text(node.body)
    orelse_text: str | None = _string_expression_text(node.orelse)
    if condition_code is None or body_text is None or orelse_text is None:
        return {}
    return {condition_code: body_text, else_branch_key: orelse_text}


def _code_equality_constant(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        return None
    if not isinstance(node.ops[0], ast.Eq):
        return None
    comparator: ast.expr = node.comparators[0]
    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
        return comparator.value
    return None


def _string_expression_text(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _joined_string_text(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left_text: str | None = _string_expression_text(node.left)
        right_text: str | None = _string_expression_text(node.right)
        if left_text is None or right_text is None:
            return None
        return f"{left_text}{right_text}"
    return None


def _joined_string_text(node: ast.JoinedStr) -> str:
    parts: list[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
            continue
        if isinstance(value, ast.FormattedValue):
            parts.append("{" + ast.unparse(value.value) + "}")
    return "".join(parts)


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message).strip()


def _render_rule_reference(rule: RuleReference) -> str:
    return f"- `{rule.code}`: {rule.message}"


def _normalize_blank_lines(contents: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", contents)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Generate the SQLBuild structure skill."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, default=default_source_path)
    parser.add_argument("--output", type=Path, default=default_output_path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
