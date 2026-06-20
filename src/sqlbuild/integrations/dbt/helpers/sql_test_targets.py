"""Adapt dbt manifest models into SQLBuild SQL test targets."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.models.sql_tests import CompiledModelSqlTestPayload, CompiledSqlTest
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
    DbtManifestSource,
)
from sqlbuild.shared.types import SqlReferenceKind


def resolve_dbt_sql_test_target_names(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_dbt_unique_ids: tuple[str, ...],
    select: tuple[str, ...],
) -> tuple[str, ...]:
    """Return expected CTE suffixes that target selected dbt models."""

    sqlbuild_model_names: frozenset[str] = frozenset(model.name for model in project.models)
    _validate_model_name_collisions(
        manifest=manifest,
        sqlbuild_model_names=sqlbuild_model_names,
    )
    selected_ids: frozenset[str] = frozenset(selected_dbt_unique_ids)
    include_all: bool = not select
    target_names: list[str] = []
    seen: set[str] = set()
    for expected_name in _expected_model_names(project=project):
        if expected_name in sqlbuild_model_names:
            continue
        dbt_model: DbtManifestModel | None = _resolve_expected_model(
            manifest=manifest,
            expected_name=expected_name,
            require_match=False,
        )
        if dbt_model is None:
            continue
        if not include_all and dbt_model.unique_id not in selected_ids:
            if not _select_matches_expected_model(select=select, dbt_model=dbt_model):
                continue
        if expected_name in seen:
            continue
        seen.add(expected_name)
        target_names.append(expected_name)
    return tuple(target_names)


def adapt_project_for_dbt_sql_tests(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    target_names: tuple[str, ...],
) -> CompiledProject:
    """Return a project with selected dbt models exposed as testable models."""

    if not target_names:
        return project
    _validate_source_relation_collisions(project=project, manifest=manifest)
    _validate_seed_relation_collisions(project=project, manifest=manifest)
    sqlbuild_model_names: frozenset[str] = frozenset(model.name for model in project.models)
    _validate_model_name_collisions(
        manifest=manifest,
        sqlbuild_model_names=sqlbuild_model_names,
    )
    target_models_by_name: dict[str, DbtManifestModel] = {}
    for target_name in target_names:
        if target_name in sqlbuild_model_names:
            continue
        dbt_model: DbtManifestModel | None = _resolve_expected_model(
            manifest=manifest,
            expected_name=target_name,
            require_match=True,
        )
        if dbt_model is None:
            continue
        target_models_by_name[target_name] = dbt_model
    if not target_models_by_name:
        return project
    model_name_by_unique_id: dict[str, str] = _build_dbt_test_model_names(
        manifest=manifest,
        target_models_by_name=target_models_by_name,
        sql_tests=project.sql_tests,
        sqlbuild_model_names=sqlbuild_model_names,
    )
    adapted_models: tuple[CompiledModel, ...] = tuple(
        _adapt_dbt_model(
            manifest=manifest,
            dbt_model=manifest.models_by_unique_id[unique_id],
            target_name=target_name,
            model_name_by_unique_id={},
        )
        for unique_id, target_name in model_name_by_unique_id.items()
    )
    return replace(
        project,
        models=(*project.models, *adapted_models),
        sql_tests=tuple(
            _expand_dbt_sql_test_expected_chain(
                sql_test=sql_test,
                manifest=manifest,
                target_models_by_name=target_models_by_name,
                model_name_by_unique_id=model_name_by_unique_id,
            )
            for sql_test in project.sql_tests
        ),
    )


def _build_dbt_test_model_names(
    *,
    manifest: DbtManifestIndex,
    target_models_by_name: dict[str, DbtManifestModel],
    sql_tests: tuple[CompiledSqlTest, ...],
    sqlbuild_model_names: frozenset[str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for sql_test in sql_tests:
        if not isinstance(sql_test.payload, CompiledModelSqlTestPayload):
            continue
        for expected_name in sql_test.payload.expected_model_names:
            dbt_model: DbtManifestModel | None = target_models_by_name.get(expected_name)
            if dbt_model is None:
                continue
            _collect_dbt_test_model_names(
                manifest=manifest,
                dbt_model=dbt_model,
                target_name=expected_name,
                mock_model_names=frozenset(sql_test.payload.mock_model_names),
                sqlbuild_model_names=sqlbuild_model_names,
                result=result,
            )
    for target_name, dbt_model in target_models_by_name.items():
        result.setdefault(dbt_model.unique_id, target_name)
    return result


def _validate_model_name_collisions(
    *, manifest: DbtManifestIndex, sqlbuild_model_names: frozenset[str]
) -> None:
    duplicate_names: tuple[str, ...] = tuple(
        sorted(name for name in sqlbuild_model_names if name in manifest.models_by_name)
    )
    if duplicate_names:
        raise DbtInteropRuntimeError(
            f"dbt and SQLBuild models share names: {', '.join(duplicate_names)}",
            help=(
                "Rename either the dbt model or SQLBuild model; shared model names are "
                "not supported."
            ),
        )


def _dbt_chain_unique_ids(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    mock_model_names: frozenset[str],
) -> tuple[str, ...]:
    unique_ids: list[str] = []
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        if dep_model is None:
            continue
        if _dbt_model_mock_name(
            manifest=manifest,
            dbt_model=dep_model,
            mock_model_names=mock_model_names,
        ):
            continue
        unique_ids.extend(
            _dbt_chain_unique_ids(
                manifest=manifest,
                dbt_model=dep_model,
                mock_model_names=mock_model_names,
            )
        )
        unique_ids.append(dep_model.unique_id)
    unique_ids.append(dbt_model.unique_id)
    return tuple(dict.fromkeys(unique_ids))


def _collect_dbt_test_model_names(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    target_name: str,
    mock_model_names: frozenset[str],
    sqlbuild_model_names: frozenset[str],
    result: dict[str, str],
) -> None:
    result.setdefault(dbt_model.unique_id, target_name)
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        if dep_model is None:
            continue
        if _dbt_model_mock_name(
            manifest=manifest,
            dbt_model=dep_model,
            mock_model_names=mock_model_names,
        ):
            continue
        dep_target_name: str = _dbt_internal_model_name(
            manifest=manifest,
            dbt_model=dep_model,
            sqlbuild_model_names=sqlbuild_model_names,
        )
        if dep_target_name in sqlbuild_model_names:
            raise DbtInteropRuntimeError(
                f"dbt model '{dep_model.unique_id}' cannot be added to SQLBuild test chain because "
                f"SQLBuild model '{dep_target_name}' already exists"
            )
        _collect_dbt_test_model_names(
            manifest=manifest,
            dbt_model=dep_model,
            target_name=dep_target_name,
            mock_model_names=mock_model_names,
            sqlbuild_model_names=sqlbuild_model_names,
            result=result,
        )


def _dbt_internal_model_name(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    sqlbuild_model_names: frozenset[str],
) -> str:
    matches: tuple[DbtManifestModel, ...] = manifest.models_by_name.get(dbt_model.name, ())
    if len(matches) == 1 and dbt_model.name not in sqlbuild_model_names:
        return dbt_model.name
    return f"{dbt_model.package_name}__{dbt_model.name}"


def _expand_dbt_sql_test_expected_chain(
    *,
    sql_test: CompiledSqlTest,
    manifest: DbtManifestIndex,
    target_models_by_name: dict[str, DbtManifestModel],
    model_name_by_unique_id: dict[str, str],
) -> CompiledSqlTest:
    if not isinstance(sql_test.payload, CompiledModelSqlTestPayload):
        return sql_test
    expected_model_names: list[str] = []
    model_query_overrides: dict[str, str] = dict(sql_test.payload.model_query_overrides)
    mock_model_names: frozenset[str] = frozenset(sql_test.payload.mock_model_names)
    for expected_name in sql_test.payload.expected_model_names:
        dbt_model: DbtManifestModel | None = target_models_by_name.get(expected_name)
        if dbt_model is None:
            expected_model_names.append(expected_name)
            continue
        chain_unique_ids: tuple[str, ...] = _dbt_chain_unique_ids(
            manifest=manifest,
            dbt_model=dbt_model,
            mock_model_names=mock_model_names,
        )
        chain_model_name_by_unique_id: dict[str, str] = {
            unique_id: model_name_by_unique_id[unique_id] for unique_id in chain_unique_ids
        }
        chain_model_name_by_unique_id.update(
            _dbt_mock_model_name_by_unique_id(
                manifest=manifest,
                dbt_model=dbt_model,
                mock_model_names=mock_model_names,
            )
        )
        for unique_id in chain_unique_ids:
            chain_model: DbtManifestModel = manifest.models_by_unique_id[unique_id]
            query_sql: str = _compiled_query_sql(dbt_model=chain_model)
            if not query_sql.strip():
                raise DbtInteropRuntimeError(
                    f"dbt model '{chain_model.unique_id}' has no compiled SQL for SQLBuild testing"
                )
            model_query_overrides[model_name_by_unique_id[unique_id]] = (
                _rewrite_direct_dbt_model_refs(
                    manifest=manifest,
                    dbt_model=chain_model,
                    query_sql=query_sql,
                    model_name_by_unique_id=chain_model_name_by_unique_id,
                )
            )
        expected_model_names.extend(
            _dbt_chain_model_names(
                manifest=manifest,
                dbt_model=dbt_model,
                mock_model_names=mock_model_names,
                model_name_by_unique_id=model_name_by_unique_id,
            )
        )
    return replace(
        sql_test,
        payload=replace(
            sql_test.payload,
            model_query_overrides=model_query_overrides,
            expected_model_names=tuple(dict.fromkeys(expected_model_names)),
        ),
    )


def _dbt_chain_model_names(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    mock_model_names: frozenset[str],
    model_name_by_unique_id: dict[str, str],
) -> tuple[str, ...]:
    names: list[str] = []
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        if dep_model is None:
            continue
        if _dbt_model_mock_name(
            manifest=manifest,
            dbt_model=dep_model,
            mock_model_names=mock_model_names,
        ):
            continue
        names.extend(
            _dbt_chain_model_names(
                manifest=manifest,
                dbt_model=dep_model,
                mock_model_names=mock_model_names,
                model_name_by_unique_id=model_name_by_unique_id,
            )
        )
        names.append(model_name_by_unique_id[dep_model.unique_id])
    names.append(model_name_by_unique_id[dbt_model.unique_id])
    return tuple(dict.fromkeys(names))


def _dbt_mock_model_name_by_unique_id(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    mock_model_names: frozenset[str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        if dep_model is None:
            continue
        mock_model_name: str | None = _dbt_model_mock_name(
            manifest=manifest,
            dbt_model=dep_model,
            mock_model_names=mock_model_names,
        )
        if mock_model_name is not None:
            result[dep_model.unique_id] = mock_model_name
            continue
        result.update(
            _dbt_mock_model_name_by_unique_id(
                manifest=manifest,
                dbt_model=dep_model,
                mock_model_names=mock_model_names,
            )
        )
    return result


def _dbt_model_mock_name(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    mock_model_names: frozenset[str],
) -> str | None:
    qualified_name: str = f"{dbt_model.package_name}__{dbt_model.name}"
    if qualified_name in mock_model_names:
        return qualified_name
    if dbt_model.name not in mock_model_names:
        return None
    matches: tuple[DbtManifestModel, ...] = manifest.models_by_name.get(dbt_model.name, ())
    if len(matches) == 1:
        return dbt_model.name
    packages: str = ", ".join(sorted(model.package_name for model in matches))
    raise DbtInteropRuntimeError(
        f"dbt model mock '__ref__{dbt_model.name}' is ambiguous across packages: {packages}",
        help=f"Use __ref__<package>__{dbt_model.name} to choose one dbt model.",
    )


def _expected_model_names(*, project: CompiledProject) -> tuple[str, ...]:
    names: list[str] = []
    for sql_test in project.sql_tests:
        if not isinstance(sql_test.payload, CompiledModelSqlTestPayload):
            continue
        names.extend(sql_test.payload.expected_model_names)
    return tuple(dict.fromkeys(names))


def _resolve_expected_model(
    *, manifest: DbtManifestIndex, expected_name: str, require_match: bool
) -> DbtManifestModel | None:
    package_name: str | None = None
    model_name: str = expected_name
    if "__" in expected_name:
        package_name, model_name = expected_name.split("__", maxsplit=1)
    if package_name is not None:
        dbt_model: DbtManifestModel | None = manifest.models_by_package_and_name.get(
            (package_name, model_name)
        )
        if dbt_model is None and require_match:
            raise DbtInteropRuntimeError(
                f"dbt model '{expected_name}' was selected for SQLBuild testing but was not found"
            )
        return dbt_model
    matches: tuple[DbtManifestModel, ...] = manifest.models_by_name.get(model_name, ())
    if len(matches) > 1:
        packages: str = ", ".join(sorted(model.package_name for model in matches))
        raise DbtInteropRuntimeError(
            f"dbt model '{model_name}' is ambiguous across packages: {packages}",
            help=f"Use __expected__<package>__{model_name} to choose one dbt model.",
        )
    if len(matches) == 0:
        if require_match:
            raise DbtInteropRuntimeError(
                f"dbt model '{expected_name}' was selected for SQLBuild testing but was not found"
            )
        return None
    return matches[0]


def _select_matches_expected_model(*, select: tuple[str, ...], dbt_model: DbtManifestModel) -> bool:
    bare_names: frozenset[str] = frozenset(
        term.removeprefix("+").removesuffix("+") for term in select
    )
    return bool(
        {
            dbt_model.name,
            dbt_model.unique_id,
            f"{dbt_model.package_name}.{dbt_model.name}",
        }
        & bare_names
    )


def _adapt_dbt_model(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    target_name: str,
    model_name_by_unique_id: dict[str, str],
) -> CompiledModel:
    query_sql: str = _compiled_query_sql(dbt_model=dbt_model)
    if not query_sql.strip():
        raise DbtInteropRuntimeError(
            f"dbt model '{dbt_model.unique_id}' has no compiled SQL for SQLBuild testing"
        )
    rewritten_sql: str = _rewrite_direct_dbt_model_refs(
        manifest=manifest,
        dbt_model=dbt_model,
        query_sql=query_sql,
        model_name_by_unique_id=model_name_by_unique_id,
    )
    references: tuple[CompileSqlReference, ...] = _dbt_ref_references(
        manifest=manifest,
        dbt_model=dbt_model,
    )
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=target_name),
        deps=(),
        name=target_name,
        relative_path=Path("dbt") / dbt_model.package_name / f"{dbt_model.name}.sql",
        query_sql=rewritten_sql,
        config=CompileModelConfig(),
        destination=CompiledRelationLocation(
            database=dbt_model.database,
            schema=dbt_model.schema,
            name=dbt_model.alias or dbt_model.name,
            qualified_name=dbt_model.relation_name,
        ),
        references=references,
        authored_sql=query_sql,
    )


def _compiled_query_sql(*, dbt_model: DbtManifestModel) -> str:
    compiled_code: object | None = dbt_model.payload.get("compiled_code")
    if isinstance(compiled_code, str) and compiled_code.strip():
        return compiled_code
    compiled_sql: object | None = dbt_model.payload.get("compiled_sql")
    if isinstance(compiled_sql, str) and compiled_sql.strip():
        return compiled_sql
    return ""


def _rewrite_direct_dbt_model_refs(
    *,
    manifest: DbtManifestIndex,
    dbt_model: DbtManifestModel,
    query_sql: str,
    model_name_by_unique_id: dict[str, str],
) -> str:
    result: str = query_sql
    dep_unique_id: str
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        dep_source: DbtManifestSource | None = manifest.sources_by_unique_id.get(dep_unique_id)
        dep_seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(dep_unique_id)
        dep_relation_name: str | None = None
        replacement: str | None = None
        if dep_model is not None:
            dep_relation_name = dep_model.relation_name
            if dep_model.unique_id in model_name_by_unique_id:
                replacement = f'__ref("{model_name_by_unique_id[dep_model.unique_id]}")'
            else:
                replacement = f'__dbt_ref("{dep_model.package_name}", "{dep_model.name}")'
        elif dep_source is not None:
            dep_relation_name = dep_source.relation_name
            replacement = (
                f'__source("{_source_fixture_name(manifest=manifest, source=dep_source)}")'
            )
        elif dep_seed is not None:
            dep_relation_name = dep_seed.relation_name
            replacement = f'__seed("{_seed_fixture_name(manifest=manifest, seed=dep_seed)}")'
        if dep_relation_name is None or replacement is None:
            continue
        before: str = result
        variant: str
        for variant in _relation_variants(relation_name=dep_relation_name):
            result = result.replace(variant, replacement)
        if result == before:
            raise DbtInteropRuntimeError(
                f"dbt model '{dbt_model.unique_id}' compiled SQL did not contain upstream relation "
                f"'{dep_relation_name}' needed for SQLBuild testing",
                help=(
                    "Recompile dbt and verify the manifest compiled SQL contains physical "
                    "relation names."
                ),
            )
    return result


def _relation_variants(*, relation_name: str) -> tuple[str, ...]:
    unquoted: str = relation_name.replace('"', "")
    parts: tuple[str, ...] = tuple(part for part in unquoted.split(".") if part)
    variants: list[str] = [relation_name, unquoted]
    if parts:
        variants.append(".".join(f'"{part}"' for part in parts))
    if len(parts) >= 2:
        variants.append(".".join(parts[-2:]))
        variants.append(".".join(f'"{part}"' for part in parts[-2:]))
    return tuple(dict.fromkeys(variant for variant in variants if variant))


def _dbt_ref_references(
    *, manifest: DbtManifestIndex, dbt_model: DbtManifestModel
) -> tuple[CompileSqlReference, ...]:
    references: list[CompileSqlReference] = []
    dep_unique_id: str
    for dep_unique_id in dbt_model.depends_on_nodes:
        dep_model: DbtManifestModel | None = manifest.models_by_unique_id.get(dep_unique_id)
        if dep_model is None:
            continue
        references.append(
            CompileSqlReference(
                ref_kind=SqlReferenceKind.DBT_REF,
                ref_package=dep_model.package_name,
                ref_name=dep_model.name,
            )
        )
    return tuple(references)


def _source_fixture_name(*, manifest: DbtManifestIndex, source: DbtManifestSource) -> str:
    matches: tuple[DbtManifestSource, ...] = tuple(
        candidate
        for candidate in manifest.sources_by_unique_id.values()
        if candidate.source_name == source.source_name and candidate.name == source.name
    )
    if len(matches) == 1:
        return f"{source.source_name}__{source.name}"
    return f"{source.package_name}__{source.source_name}__{source.name}"


def _seed_fixture_name(*, manifest: DbtManifestIndex, seed: DbtManifestSeed) -> str:
    matches: tuple[DbtManifestSeed, ...] = tuple(
        candidate
        for candidate in manifest.seeds_by_unique_id.values()
        if candidate.name == seed.name
    )
    if len(matches) == 1:
        return seed.name
    return f"{seed.package_name}__{seed.name}"


def _validate_source_relation_collisions(
    *, project: CompiledProject, manifest: DbtManifestIndex
) -> None:
    sqlbuild_relations: dict[str, str] = {}
    for source in project.sources:
        relation_key: str | None = _sqlbuild_source_relation_key(source.source_entry)
        if relation_key is None:
            continue
        sqlbuild_relations[relation_key] = source.name
    for dbt_source in manifest.sources_by_unique_id.values():
        relation_key = _normalize_relation_name(dbt_source.relation_name)
        sqlbuild_source_name: str | None = sqlbuild_relations.get(relation_key)
        if sqlbuild_source_name is None:
            continue
        raise DbtInteropRuntimeError(
            f"dbt source '{dbt_source.unique_id}' resolves to the same relation as SQLBuild "
            f"source '{sqlbuild_source_name}'",
            help="Rename or remove one source before using dbt source mocks in SQLBuild tests.",
        )


def _validate_seed_relation_collisions(
    *, project: CompiledProject, manifest: DbtManifestIndex
) -> None:
    sqlbuild_relations: dict[str, str] = {
        _compiled_relation_key(relation=seed.destination): seed.name for seed in project.seeds
    }
    for dbt_seed in manifest.seeds_by_unique_id.values():
        relation_key: str = _normalize_relation_name(dbt_seed.relation_name)
        sqlbuild_seed_name: str | None = sqlbuild_relations.get(relation_key)
        if sqlbuild_seed_name is None:
            continue
        raise DbtInteropRuntimeError(
            f"dbt seed '{dbt_seed.unique_id}' resolves to the same relation as SQLBuild seed "
            f"'{sqlbuild_seed_name}'",
            help="Rename or remove one seed before using dbt seed mocks in SQLBuild tests.",
        )


def _sqlbuild_source_relation_key(source_entry: object) -> str | None:
    database: object | None = getattr(source_entry, "database", None)
    schema: object | None = getattr(source_entry, "schema", None)
    table: object | None = getattr(source_entry, "table", None)
    name: object | None = getattr(source_entry, "name", None)
    relation_parts: tuple[str, ...] = tuple(
        str(part) for part in (database, schema, table or name) if isinstance(part, str) and part
    )
    if not relation_parts:
        return None
    return _normalize_relation_name(".".join(relation_parts))


def _compiled_relation_key(*, relation: CompiledRelationLocation) -> str:
    if relation.qualified_name is not None:
        return _normalize_relation_name(relation.qualified_name)
    relation_parts: tuple[str, ...] = tuple(
        part for part in (relation.database, relation.schema, relation.name) if part
    )
    return _normalize_relation_name(".".join(relation_parts))


def _normalize_relation_name(relation_name: str) -> str:
    return relation_name.replace('"', "").lower()
