"""Targeted warehouse identity state for direct seed commands."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledSeed
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME, NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet


def read_seed_fingerprints(
    *, adapter: BaseAdapter, connection: Any, seeds: tuple[CompiledSeed, ...]
) -> dict[str, Fingerprint]:
    """Read only fingerprint state required to classify selected direct seeds."""

    names_by_target: dict[tuple[str | None, str], set[str]] = {}
    for seed in seeds:
        if seed.destination.schema is None:
            continue
        names_by_target.setdefault((seed.destination.database, seed.destination.schema), set()).add(
            seed.name
        )

    targets: tuple[tuple[str | None, str], ...] = tuple(
        sorted(names_by_target, key=lambda target: ((target[0] or ""), target[1]))
    )
    relations_by_target: dict[tuple[str | None, str], tuple[RelationInfo, ...]] = (
        _gather_fingerprint_relations(
            adapter=adapter,
            connection=connection,
            targets=targets,
        )
    )
    fingerprints: dict[str, Fingerprint] = {}
    for database, schema in targets:
        names: set[str] = names_by_target[(database, schema)]
        relations: tuple[RelationInfo, ...] = relations_by_target[(database, schema)]
        table_exists: bool = any(
            relation.name.lower() == FINGERPRINT_TABLE_NAME.lower() for relation in relations
        )
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            table_exists=table_exists,
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
            node_names=tuple(sorted(names)),
        )
        fingerprints.update(
            {
                name: fingerprint
                for name, fingerprint in fingerprint_set.fingerprints.items()
                if fingerprint.node_type == NODE_TYPE_SEED and name in names
            }
        )
    return fingerprints


def _gather_fingerprint_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    targets: tuple[tuple[str | None, str], ...],
) -> dict[tuple[str | None, str], tuple[RelationInfo, ...]]:
    if not targets:
        return {}
    database, schema = targets[0]
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=database,
        schemas=(schema,),
        names=(FINGERPRINT_TABLE_NAME,),
    )
    return {
        (database, schema): relations,
        **_gather_fingerprint_relations(
            adapter=adapter,
            connection=connection,
            targets=targets[1:],
        ),
    }
