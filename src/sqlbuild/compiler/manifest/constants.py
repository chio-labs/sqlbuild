"""Manifest output constants aligned with dbt manifest v12 schema."""

from sqlbuild.compiler.compile.types import CompiledResourceType

DBT_MANIFEST_SCHEMA_VERSION: str = "https://schemas.getdbt.com/dbt/manifest/v12.json"

RESOURCE_TYPE_MODEL: str = "model"
RESOURCE_TYPE_SOURCE: str = "source"
RESOURCE_TYPE_SEED: str = "seed"
RESOURCE_TYPE_TEST: str = "test"
RESOURCE_TYPE_MACRO: str = "macro"

CHECKSUM_HASH_NAME: str = "sha256"

RESOURCE_TYPE_PREFIX: dict[str, str] = {
    CompiledResourceType.MODEL: "model",
    CompiledResourceType.SOURCE: "source",
    CompiledResourceType.SEED: "seed",
    CompiledResourceType.DBT_REF: "model",
    CompiledResourceType.AUDIT: "test",
    CompiledResourceType.SQL_TEST: "test",
}
