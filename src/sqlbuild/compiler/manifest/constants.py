"""Manifest output constants aligned with dbt manifest v12 schema."""

DBT_MANIFEST_SCHEMA_VERSION: str = "https://schemas.getdbt.com/dbt/manifest/v12.json"

RESOURCE_TYPE_MODEL: str = "model"
RESOURCE_TYPE_SOURCE: str = "source"
RESOURCE_TYPE_SEED: str = "seed"
RESOURCE_TYPE_TEST: str = "test"
RESOURCE_TYPE_MACRO: str = "macro"

CHECKSUM_HASH_NAME: str = "sha256"
