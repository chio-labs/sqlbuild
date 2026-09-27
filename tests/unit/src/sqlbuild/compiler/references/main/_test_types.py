"""Test case types for public SQL reference entries."""

from dataclasses import dataclass

from sqlbuild.compiler.references.models import RelationName
from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class AssertNoUnresolvedSqlMarkersTestCase:
    description: str
    sql: str
    context: str
    expected_error_fragment: str
    expected_code: str | None = None


@dataclass(frozen=True)
class ExtractRelationNamesTestCase:
    """SQL text and the relations and temporary tables it names."""

    description: str
    sql: str
    dialect: str
    expected_relations: tuple[RelationName, ...]
    expected_temporary: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MatchProjectRelationTestCase:
    """A relation named in SQL and the project relation it resolves to, if any."""

    description: str
    relation: RelationName
    default_schema: str | None
    expected_ref: SqlResourceRef | None


@dataclass(frozen=True)
class UnparseableRelationNamesTestCase:
    """SQL that cannot be parsed, which the hard-coded name checks must never block."""

    description: str
    sql: str
    expected_result: None
