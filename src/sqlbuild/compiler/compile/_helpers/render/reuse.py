"""Route project-wide renders through the active render reuse session, if any."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.sources import build_source_inputs
from sqlbuild.compiler.compile._helpers.attachment.sql_tests import (
    build_scenario_inputs,
    build_test_inputs_with_cache,
)
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import (
    COMPILE_RENDER_REUSE,
    RENDER_REUSE_SCENARIOS_GROUP,
    RENDER_REUSE_SOURCES_GROUP,
    RENDER_REUSE_TESTS_GROUP,
)
from sqlbuild.compiler.compile.models import (
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
    ModelInputBuildContext,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver


def reused_or_rendered[T](
    *, render_reuse: CompileRenderReuseSession | None, name: str, render: Callable[[], T]
) -> T:
    """Return the stored render of one project-wide group, or render and record it."""

    return render() if render_reuse is None else render_reuse.group(name=name, render=render)


def claimed_render_reuse(
    *, discovered_inputs: DiscoveredProjectInputs
) -> CompileRenderReuseSession | None:
    """Claim the active render reuse session, if any, and plan it for the discovered models."""

    render_reuse: CompileRenderReuseSession | None = COMPILE_RENDER_REUSE.claim()
    if render_reuse is not None:
        render_reuse.plan_models(model_files=discovered_inputs.model_files)
    return render_reuse


def build_sql_resource_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...],
    no_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    compile_cache_dir: Path | None,
    render_reuse: CompileRenderReuseSession | None,
) -> tuple[
    tuple[CompileSourceInput, ...],
    tuple[CompileSqlTestInput, ...],
    tuple[CompileSqlScenarioInput, ...],
]:
    """Render sources, tests, and scenarios, each reused whole after model-only edits."""

    source_inputs: tuple[CompileSourceInput, ...] = reused_or_rendered(
        render_reuse=render_reuse,
        name=RENDER_REUSE_SOURCES_GROUP,
        render=partial(
            build_source_inputs,
            discovered_inputs=discovered_inputs,
            effective_vars=context.effective_vars,
            effective_settings=context.effective_settings,
            macro_context=context.macro_context,
            loaded_macros=context.loaded_macros,
            declaration_expansion=context.declaration_expansion,
            no_sql_validation=no_sql_validation,
        ),
    )
    test_inputs: tuple[CompileSqlTestInput, ...] = reused_or_rendered(
        render_reuse=render_reuse,
        name=RENDER_REUSE_TESTS_GROUP,
        render=partial(
            build_test_inputs_with_cache,
            discovered_inputs=discovered_inputs,
            effective_vars=context.effective_vars,
            macro_context=context.macro_context,
            loaded_macros=context.loaded_macros,
            declaration_expansion=context.declaration_expansion,
            external_sql_reference_resolver=external_sql_reference_resolver,
            sql_function_inputs=sql_function_inputs,
            compile_cache_dir=compile_cache_dir,
            sql_lexical_syntax=context.sql_lexical_syntax,
        ),
    )
    scenario_inputs: tuple[CompileSqlScenarioInput, ...] = reused_or_rendered(
        render_reuse=render_reuse,
        name=RENDER_REUSE_SCENARIOS_GROUP,
        render=partial(
            build_scenario_inputs,
            discovered_inputs=discovered_inputs,
            effective_vars=context.effective_vars,
            macro_context=context.macro_context,
            loaded_macros=context.loaded_macros,
            declaration_expansion=context.declaration_expansion,
            external_sql_reference_resolver=external_sql_reference_resolver,
            sql_lexical_syntax=context.sql_lexical_syntax,
        ),
    )
    return source_inputs, test_inputs, scenario_inputs
