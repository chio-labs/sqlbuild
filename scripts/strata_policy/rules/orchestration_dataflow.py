"""Repository-specific orchestration dataflow rules."""

from __future__ import annotations

from strata import (
    DefinitionIdentity,
    Family,
    Fault,
    NamedCallFact,
    ParameterMutationOccurrenceFact,
    RuleContext,
    rule,
)

from scripts.strata_policy._helpers.metadata_calls import (
    metadata_bearing_helper_names,
    metadata_call_label,
)
from scripts.strata_policy._helpers.orchestration_dataflow import (
    discarded_call_name_is_allowed,
)
from scripts.strata_policy._helpers.path_checks import is_adapter_implementation_path
from scripts.strata_policy.constants import (
    ALLOWED_METADATA_LOOP_PATHS,
    ALLOWED_PARAMETER_MUTATION_COMMENT,
    COMPILER_EXECUTOR_DOMAIN_NAMES,
    HELPERS_PACKAGE_NAME,
    INIT_MODULE_NAME,
    NAME_REFERENCE_KIND,
    NESTED_HELPER_MODULE_MIN_PARTS,
    POLICY_EVALUATION_SCOPES,
    ROOT_SCOPE_NAME,
    RUNTIME_ROOT_PARTS,
)


@rule(
    code="XSB051",
    family=Family.CUSTOM,
    slug="metadata-query-loop",
    message="warehouse metadata calls must not run once per loop iteration",
    remediation="Gather metadata once into a relation lookup or WarehouseSnapshot before looping.",
)
def metadata_query_loop(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path in ALLOWED_METADATA_LOOP_PATHS or is_adapter_implementation_path(path=path):
        return []
    bearing_method_names, bearing_function_names = metadata_bearing_helper_names(ctx=ctx)
    faults: list[Fault] = []
    call: NamedCallFact
    for call in ctx.facts.named_calls():
        if not call.inside_loop:
            continue
        label: str | None = metadata_call_label(
            call=call,
            bearing_method_names=bearing_method_names,
            bearing_function_names=bearing_function_names,
        )
        if label is not None:
            faults.append(
                ctx.fault_at(
                    location=call.location,
                    message=(
                        f"'{label}' reaches a warehouse metadata call inside a loop and risks "
                        "N+1 warehouse queries"
                    ),
                )
            )
    return faults


@rule(
    code="XSB066",
    family=Family.CUSTOM,
    slug="main-discarded-call",
    message="main orchestrators must consume bare phase call results",
    remediation="Assign, return, or explicitly discard the result with _ = call(...).",
)
def main_discarded_call(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    if not ctx.is_main_module() or ctx.path.name == INIT_MODULE_NAME:
        return []
    top_level_function_keys: frozenset[tuple[str, int, int]] = frozenset(
        (function.name, function.location.line, function.location.column)
        for function in ctx.facts.functions().top_level
    )
    faults: list[Fault] = []
    call: NamedCallFact
    for call in ctx.facts.named_calls():
        if (
            not call.bare_expression
            or call.reference is None
            or call.reference.kind != NAME_REFERENCE_KIND
            or not call.enclosing_functions
        ):
            continue
        outermost_function: DefinitionIdentity = call.enclosing_functions[-1]
        outermost_key: tuple[str, int, int] = (
            outermost_function.name,
            outermost_function.location.line,
            outermost_function.location.column,
        )
        if outermost_key not in top_level_function_keys:
            continue
        call_name: str | None = call.reference.base_name
        if call_name is not None and not discarded_call_name_is_allowed(name=call_name):
            faults.append(ctx.fault_at(location=call.location))
    return faults


@rule(
    code="XSB067",
    family=Family.CUSTOM,
    slug="phase-parameter-mutation",
    message="compiler and executor phase helpers must not mutate input parameters",
    remediation=(
        "Return updated values, or mark a deliberate builder with # sc: allow-param-mutation."
    ),
)
def phase_parameter_mutation(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if (
        len(parts) < NESTED_HELPER_MODULE_MIN_PARTS
        or parts[:2] != RUNTIME_ROOT_PARTS
        or parts[2] not in COMPILER_EXECUTOR_DOMAIN_NAMES
        or HELPERS_PACKAGE_NAME not in parts[3:-1]
    ):
        return []
    faults: list[Fault] = []
    mutation: ParameterMutationOccurrenceFact
    for mutation in ctx.facts.parameter_mutation_occurrences():
        if ALLOWED_PARAMETER_MUTATION_COMMENT in ctx.text.line(mutation.location.line):
            continue
        faults.append(
            ctx.fault_at(
                location=mutation.location,
                message=f"'{mutation.parameter_name}' is a parameter and is mutated here",
            )
        )
    return faults
