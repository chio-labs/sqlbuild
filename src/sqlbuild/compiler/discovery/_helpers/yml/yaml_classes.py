"""The Python classes native YAML entry parsing builds source and seed declarations as."""

from __future__ import annotations

from functools import cache

from sqlbuild.compiler.model_config.main._native_contract_classes import native_contract_classes
from sqlbuild.integrations.dlt.models import DltResourceConfig, DltSourceConfig
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.contracts.models import (
    IntegrationLoaderConfig,
    SchemaSeedEntry,
    SeedCsvSettings,
    SourceColumnEntry,
    SourceEntry,
    SourceFreshnessAgePolicy,
    SourceFreshnessConfig,
)
from sqlbuild.spec.contracts.types import (
    SourceFreshnessStrategy,
    SourceFreshnessValueKind,
    SourceWriteStrategy,
)


@cache
def yaml_entry_classes() -> dict[str, object]:
    """The classes parsed seed and source declarations become."""

    return {
        "contracts": native_contract_classes(),
        "schema_seed_entry": SchemaSeedEntry,
        "seed_csv_settings": SeedCsvSettings,
        "source_entry": SourceEntry,
        "source_column_entry": SourceColumnEntry,
        "source_freshness_config": SourceFreshnessConfig,
        "source_freshness_age_policy": SourceFreshnessAgePolicy,
        "integration_loader_config": IntegrationLoaderConfig,
        "ingestr_source_config": IngestrSourceConfig,
        "dlt_source_config": DltSourceConfig,
        "dlt_resource_config": DltResourceConfig,
        "source_write_strategy": SourceWriteStrategy,
        "source_freshness_strategy": SourceFreshnessStrategy,
        "source_freshness_value_kind": SourceFreshnessValueKind,
    }
