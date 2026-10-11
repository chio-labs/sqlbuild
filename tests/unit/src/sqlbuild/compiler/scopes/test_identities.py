"""Tests for qualified resource and declaration identities."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main.explain_scope_declaration import explain_scope_declaration
from sqlbuild.compiler.scopes.main.query_scope_report import query_scope_report
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationIdentity,
    ScopeDiagnostic,
    ScopeLookup,
    ScopeReport,
)
from sqlbuild.compiler.scopes.types import DeclarationKind
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
    IdentityReportCase,
    InvalidIdentityCase,
    QualifiedIdentityCase,
)
from tests.unit.src.sqlbuild.compiler.scopes.helpers import scope_index


@pytest.mark.parametrize(
    "test_case",
    [IdentityReportCase("resource", "model:stg_orders", "model:stg_orders", ())],
    ids=lambda case: case.description,
)
def test_given_qualified_resource_when_querying_then_report_names_the_same_identity(
    test_case: IdentityReportCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    report: ScopeReport = query_scope_report(lookup=lookup, target=test_case.text)

    assert report.resource.identity == test_case.expected_identity
    assert tuple(item.message for item in report.diagnostics) == test_case.expected_messages


@pytest.mark.parametrize(
    "test_case",
    [IdentityReportCase("public_declaration", "enum:order_status", "enum:order_status", ())],
    ids=lambda case: case.description,
)
def test_given_qualified_declaration_when_explaining_then_identity_round_trips(
    test_case: IdentityReportCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    explanation: DeclarationExplanation
    diagnostics: tuple[ScopeDiagnostic, ...]
    explanation, diagnostics = explain_scope_declaration(lookup=lookup, declaration=test_case.text)

    assert explanation.declaration is not None
    assert explanation.declaration.identity == test_case.expected_identity
    assert tuple(item.message for item in diagnostics) == test_case.expected_messages


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityReportCase(
            "private_owner_qualified_declaration",
            "constant:model:stg_orders._minimum_value",
            None,
            (
                "Target 'constant:model:stg_orders._minimum_value' is not valid for this "
                "scope query",
            ),
        ),
        IdentityReportCase(
            "unknown_kind",
            "widget:orders",
            None,
            ("Target 'widget:orders' is not valid for this scope query",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_declaration_when_explaining_then_reports_its_formatted_identity(
    test_case: IdentityReportCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    explanation: DeclarationExplanation
    diagnostics: tuple[ScopeDiagnostic, ...]
    explanation, diagnostics = explain_scope_declaration(lookup=lookup, declaration=test_case.text)

    assert explanation.declaration is test_case.expected_identity
    assert tuple(item.message for item in diagnostics) == test_case.expected_messages


@pytest.mark.parametrize(
    "test_case",
    [
        QualifiedIdentityCase(
            "cross_kind", "order_status", DeclarationIdentity(DeclarationKind.ENUM, "order_status")
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cross_kind_same_name_when_constructing_identities_then_they_remain_distinct(
    test_case: QualifiedIdentityCase,
) -> None:
    identities: set[DeclarationIdentity] = {
        DeclarationIdentity(kind=kind, name="order_status") for kind in DeclarationKind
    }

    assert test_case.expected_identity in identities


@pytest.mark.parametrize(
    "test_case",
    [InvalidIdentityCase("too_many_parts", "model:a:b:c", InvalidQualifiedIdentityError)],
    ids=lambda case: case.description,
)
def test_given_unparseable_context_identity_when_explaining_then_rejects_unqualified_identity(
    test_case: InvalidIdentityCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    with pytest.raises(test_case.expected_error, match="kind-qualified"):
        explain_scope_declaration(
            lookup=lookup, declaration="enum:order_status", target=test_case.value
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
