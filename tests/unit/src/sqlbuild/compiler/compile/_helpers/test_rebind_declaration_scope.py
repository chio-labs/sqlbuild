"""Rebinding a built declaration index to privately loaded macro instances."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.attachment.declaration_scope import (
    build_declaration_scope,
    rebind_declaration_scope,
)
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models import DeclarationScopeBuild, LoadedMacro
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.models import DeclarationIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    RebindDeclarationScopeTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    write_scoped_macro_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RebindDeclarationScopeTestCase(
            description="global macro", macro_name="order_filter", expected_rebound=True
        ),
        RebindDeclarationScopeTestCase(
            description="test-scoped macro", macro_name="row_limit", expected_rebound=True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_same_discovery_when_rebinding_private_macros_then_index_matches_a_fresh_build(
    test_case: RebindDeclarationScopeTestCase,
    tmp_path: Path,
) -> None:
    write_scoped_macro_orders_project(tmp_path)
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    shared: DeclarationScopeBuild = build_declaration_scope(
        discovered_inputs=discovered,
        loaded_macros=load_project_macros(discovered.macro_files),
    )
    private_macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)

    rebound: DeclarationScopeBuild | None = rebind_declaration_scope(
        scope=shared, discovered_inputs=discovered, loaded_macros=private_macros
    )

    assert (rebound is not None) is test_case.expected_rebound
    assert rebound is not None
    fresh: DeclarationScopeBuild = build_declaration_scope(
        discovered_inputs=discovered, loaded_macros=private_macros
    )
    identity: DeclarationIdentity = DeclarationIdentity(DeclarationKind.MACRO, test_case.macro_name)
    private_value: object = rebound.resolver.projection.declarations[identity]
    shared_value: object = shared.resolver.projection.declarations[identity]
    assert rebound.index is shared.index
    assert rebound.index == fresh.index
    assert rebound.loaded_macros is private_macros
    assert private_value is private_macros[test_case.macro_name]
    assert isinstance(shared_value, LoadedMacro)
    assert private_macros[test_case.macro_name].function is not shared_value.function


@pytest.mark.parametrize(
    "test_case",
    [
        RebindDeclarationScopeTestCase(
            description="different macro source",
            macro_name="row_limit",
            expected_rebound=False,
            private_macro_source='def row_limit() -> str:\n    return "LIMIT 2"\n',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_different_private_macro_metadata_when_rebinding_then_full_build_is_required(
    test_case: RebindDeclarationScopeTestCase,
    tmp_path: Path,
) -> None:
    write_scoped_macro_orders_project(tmp_path)
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    shared: DeclarationScopeBuild = build_declaration_scope(
        discovered_inputs=discovered,
        loaded_macros=load_project_macros(discovered.macro_files),
    )
    private_macros: dict[str, LoadedMacro] = load_project_macros(discovered.macro_files)
    private_macros[test_case.macro_name] = replace(
        private_macros[test_case.macro_name], raw_source=str(test_case.private_macro_source)
    )

    rebound: DeclarationScopeBuild | None = rebind_declaration_scope(
        scope=shared, discovered_inputs=discovered, loaded_macros=private_macros
    )

    assert (rebound is not None) is test_case.expected_rebound


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
