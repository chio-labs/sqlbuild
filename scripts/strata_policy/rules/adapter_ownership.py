"""Repository-specific adapter implementation ownership rules."""

from __future__ import annotations

from strata import (
    AssignmentReferenceFact,
    ClassDeclarationFact,
    Family,
    Fault,
    NamedCallFact,
    RuleContext,
    rule,
)

from scripts.strata_policy._helpers.adapter_contracts import (
    abstract_adapter_method_names,
    adapter_contract_class_names,
)
from scripts.strata_policy.constants import (
    BASE_ADAPTER_CLASS_NAME,
    BASE_ADAPTER_REFERENCE_PART_COUNT,
)


@rule(
    code="XSB037",
    family=Family.CUSTOM,
    slug="adapter-method-alias",
    message="first-class adapter methods must not alias BaseAdapter implementations",
    remediation="Copy the implementation into the owning adapter class so overrides are explicit.",
)
def adapter_method_alias(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    checked_class_names: frozenset[str] = adapter_contract_class_names(
        path_parts=ctx.repo_relative_parts(),
        ctx=ctx,
    )
    faults: list[Fault] = []
    assignment: AssignmentReferenceFact
    for assignment in ctx.facts.assignment_references():
        if (
            assignment.owning_class is None
            or assignment.owning_class.name not in checked_class_names
            or assignment.owning_function is not None
            or assignment.value_reference is None
        ):
            continue
        if (
            assignment.value_reference.parts[:1] == (BASE_ADAPTER_CLASS_NAME,)
            and len(assignment.value_reference.parts) == BASE_ADAPTER_REFERENCE_PART_COUNT
        ):
            faults.append(ctx.fault_at(location=assignment.location))
    return faults


@rule(
    code="XSB038",
    family=Family.CUSTOM,
    slug="adapter-super-delegation",
    message="first-class adapter contract methods must not delegate to super()",
    remediation="Own the complete contract method implementation in the adapter class.",
)
def adapter_super_delegation(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    checked_class_names: frozenset[str] = adapter_contract_class_names(
        path_parts=ctx.repo_relative_parts(),
        ctx=ctx,
    )
    if not checked_class_names:
        return []
    contract_methods: frozenset[str] = abstract_adapter_method_names(ctx=ctx)
    faults: list[Fault] = []
    calls: tuple[NamedCallFact, ...] = ctx.facts.named_calls()
    declaration: ClassDeclarationFact
    for declaration in ctx.facts.class_declarations():
        if not declaration.top_level or declaration.name not in checked_class_names:
            continue
        for method in declaration.methods:
            if method.name not in contract_methods:
                continue
            method_has_super_call: bool = False
            for call in calls:
                if call.super_call and any(
                    owner.name == method.name and owner.location == method.location
                    for owner in call.enclosing_functions
                ):
                    method_has_super_call = True
                    break
            if method_has_super_call:
                faults.append(ctx.fault_at(location=method.location))
    return faults
