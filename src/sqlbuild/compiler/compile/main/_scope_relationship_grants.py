"""Compiler extraction of test and scenario declaration grants."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.attachment.scope_relationships import (
    build_scope_relationship_grants as _build_scope_relationship_grants,
)
from sqlbuild.compiler.compile.models import ScopeRelationshipBuild
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.models import ScopeIndex


def build_scope_relationship_grants(
    *, discovered_inputs: DiscoveredProjectInputs, index: ScopeIndex
) -> ScopeRelationshipBuild:
    """Return expected-model grants while retaining independent extraction faults."""

    return _build_scope_relationship_grants(discovered_inputs=discovered_inputs, index=index)
