from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalTargetTestCase:
    description: str
    model_name: str
    version_hash: str
    expected_schema: str
    expected_name: str


@dataclass(frozen=True)
class RelationTypeTestCase:
    description: str
    materialized: str | None
    expected_relation_type: str


@dataclass(frozen=True)
class RewrittenTargetsTestCase:
    description: str
    selected_model_version_hashes: dict[str, str]
    bound_relations: dict[str, str]
    expected_selected_name: str
    expected_bound_name: str


@dataclass(frozen=True)
class RewriteProjectTargetsTestCase:
    description: str
    selected_model_version_hashes: dict[str, str]
    expected_rewritten_name: str
