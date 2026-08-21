"""Built-in layer, naming, reference, and contract rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.kata_engine._helpers.sql.ast import nodes, table_parts
from sqlbuild.kata_engine._helpers.sql.model_name import apparent_layer, parse_model_name
from sqlbuild.kata_engine.constants import (
    CONTRACT_ENFORCED,
    LAYER_INT_CLEAN,
    LAYER_INT_ENRICHED,
    LAYER_INT_VIEW,
    REFERENCE_KIND_REF,
)
from sqlbuild.kata_engine.models import KataFault, KataRule, ModelNameParts
from sqlbuild.kata_engine.types import RuleContext

_LAYER_ORDER: dict[str, int] = {
    "stg": 0,
    "stg_v": 0,
    "int_clean": 1,
    "int_v": 2,
    "int_enriched": 2,
    "mart": 3,
    "mart_v": 3,
}


def _rule(
    *,
    code: str,
    slug: str,
    message: str,
    remediation: str,
    check: Any,
    enabled_by_default: bool = False,
) -> KataRule:
    return KataRule(
        code=code,
        family="layers",
        slug=slug,
        message=message,
        remediation=remediation,
        check=check,
        enabled_by_default=enabled_by_default,
    )


def forward_refs(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    current: ModelNameParts | None = parse_model_name(model.name)
    if current is None:
        return []
    faults: list[KataFault] = []
    for reference in model.references:
        if str(reference.ref_kind) != REFERENCE_KIND_REF:
            continue
        upstream: ModelNameParts | None = parse_model_name(reference.ref_name)
        if upstream is not None and _LAYER_ORDER[upstream.layer] > _LAYER_ORDER[current.layer]:
            faults.append(
                ctx.path_fault(
                    message=(
                        f"{model.name} reaches forward from {current.layer} to "
                        f"{upstream.layer} via {reference.ref_name}"
                    )
                )
            )
    return faults


def raw_qualified_tables(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for table in nodes(root=ctx.ast, wanted="table"):
        parts: tuple[str, str, str] = table_parts(table)
        if not parts[0] and not parts[1]:
            continue
        qualified_name: str = ".".join(part for part in parts if part)
        faults.append(
            ctx.fault(
                node=table,
                message=f"raw qualified table {qualified_name!r} bypasses the SQLBuild graph",
            )
        )
    return faults


def name_grammar(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    parts: ModelNameParts | None = parse_model_name(model.name)
    if parts is not None:
        if ctx.kata_config.domains and parts.domain not in ctx.kata_config.domains:
            return [
                ctx.path_fault(
                    message=f"model {model.name!r} uses unknown domain {parts.domain!r}",
                    remediation=(
                        "Rename the model into a configured kata domain, or add this domain to "
                        "kata.domains when it is an intentional project owner."
                    ),
                )
            ]
        return []
    layer: str | None = apparent_layer(model.name)
    message: str = f"model {model.name!r} does not follow <domain>__<layer>__<entity>[__<source>]"
    if layer is not None and layer.startswith("int"):
        message = f"model {model.name!r} uses unsupported intermediate layer {layer!r}"
    return [ctx.path_fault(message=message)]


def folder_layer(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    parts: ModelNameParts | None = parse_model_name(model.name)
    if parts is None:
        return []
    expected_parts: tuple[str, ...]
    if parts.layer.startswith("stg"):
        expected_parts = ("staging",)
    elif parts.layer == LAYER_INT_CLEAN:
        expected_parts = ("intermediate", "clean")
    elif parts.layer == LAYER_INT_ENRICHED:
        expected_parts = ("intermediate", "enriched")
    elif parts.layer == LAYER_INT_VIEW:
        expected_parts = ("intermediate",)
    else:
        expected_parts = ("mart",)
    expected: str = "/".join(expected_parts)
    path_parts: tuple[str, ...] = Path(model.relative_path).parent.parts
    placement_matches: bool = any(
        path_parts[index : index + len(expected_parts)] == expected_parts
        for index in range(len(path_parts))
    )
    return (
        []
        if placement_matches
        else [
            ctx.path_fault(
                message=f"{parts.layer} model {model.name!r} must live under a {expected}/ folder"
            )
        ]
    )


def contract_required(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    return (
        [] if str(model.config.values.get("contract")) == CONTRACT_ENFORCED else [ctx.path_fault()]
    )


def source_token_policy(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    parts: ModelNameParts | None = parse_model_name(model.name)
    source_tokens: list[str] = []
    if parts is not None and parts.source is not None:
        source_tokens.append(parts.source)
    for reference in model.references:
        if str(reference.ref_kind) != REFERENCE_KIND_REF:
            source_tokens.append(reference.ref_name)
    replacement: str | None = None
    retired: str | None = None
    for token in source_tokens:
        configured_replacement: str | None = ctx.kata_config.retired_source_tokens.get(token)
        if configured_replacement is not None:
            retired = token
            replacement = configured_replacement
            break
    if replacement is not None:
        return [
            ctx.path_fault(
                message=f"model {model.name!r} uses retired source token {retired!r}",
                remediation=(
                    f"Rename the model's source token to {replacement!r}; update references at "
                    "the same model path."
                ),
            )
        ]
    approved: tuple[str, ...] = ctx.kata_config.approved_source_tokens
    unapproved: str | None = (
        next(
            (token for token in source_tokens if token not in approved),
            None,
        )
        if approved
        else None
    )
    if unapproved is not None:
        return [
            ctx.path_fault(
                message=f"model {model.name!r} uses unapproved source token {unapproved!r}",
                remediation=(
                    "Rename the source suffix to a token listed in kata.approved_source_tokens "
                    "at this model path."
                ),
            )
        ]
    return []


def reference_name_policy(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    faults: list[KataFault] = []
    for reference in model.references:
        if str(reference.ref_kind) != REFERENCE_KIND_REF:
            continue
        if parse_model_name(reference.ref_name) is None:
            faults.append(
                ctx.path_fault(
                    message=f"reference {reference.ref_name!r} does not follow kata model grammar",
                    remediation=(
                        "Rename the referenced model to <domain>__<layer>__<entity>"
                        "[__<source>] and update this __ref at the current model path."
                    ),
                )
            )
    return faults


def layer_rules() -> tuple[KataRule, ...]:
    """Return built-in layer and role rules."""

    return (
        _rule(
            code="KTL001",
            slug="forward-only-references",
            message="model dependencies must flow forward through the layer order",
            remediation=(
                "Move the dependency logic to the current or an earlier layer; skipping layers "
                "forward is allowed, reaching backward from an earlier layer is not."
            ),
            check=forward_refs,
        ),
        _rule(
            code="KTL101",
            slug="declared-table-references",
            message="table dependencies must use __ref or __source",
            remediation=(
                'Replace this qualified table with __ref("<model>") or __source("<source>") '
                "so it participates in the DAG."
            ),
            check=raw_qualified_tables,
        ),
        _rule(
            code="KTR001",
            slug="model-name-grammar",
            message="model names must use the closed kata layer grammar",
            remediation=(
                "Rename deterministic conforming work to int_clean and cross-source resolution "
                "work to int_enriched; express additional steps in the entity suffix."
            ),
            check=name_grammar,
        ),
        _rule(
            code="KTR002",
            slug="folder-layer",
            message="model layer names must match their folders",
            remediation=(
                "Move the model beneath staging/, intermediate/, or mart/ to match its name, "
                "or rename it for the folder that owns it."
            ),
            check=folder_layer,
        ),
        _rule(
            code="KTR201",
            slug="source-token-policy",
            message="model source suffixes must use approved, current tokens",
            remediation="Rename the source suffix at this model path to the configured token.",
            check=source_token_policy,
        ),
        _rule(
            code="KTR301",
            slug="reference-name-policy",
            message="referenced model identifiers must follow kata naming grammar",
            remediation="Rename the referenced model and this __ref to the kata model grammar.",
            check=reference_name_policy,
        ),
        _rule(
            code="KTR401",
            slug="contract-enforced-required",
            message="models must declare an enforced output contract",
            remediation=(
                "Declare contract enforced and list the authoritative output columns in MODEL()."
            ),
            check=contract_required,
            enabled_by_default=True,
        ),
    )
