"""Compile-time dbt reference resolver."""

from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.integrations.dbt.main.manifest.resolve_reference_relation import (
    resolve_dbt_reference_relation,
)
from sqlbuild.integrations.dbt.main.manifest.validate_compile_model_names import (
    validate_compile_model_names,
)
from sqlbuild.integrations.dbt.main.manifest.validate_compile_model_reference import (
    validate_compile_model_reference,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


class DbtCompileReferenceResolver:
    """External reference resolver backed by a dbt manifest index."""

    def __init__(self, *, dbt_manifest: DbtManifestIndex | None) -> None:
        self._dbt_manifest = dbt_manifest

    def validate_model_names(self, *, known_model_names: set[str]) -> None:
        validate_compile_model_names(
            known_model_names=known_model_names,
            dbt_manifest=self._dbt_manifest,
        )

    def extend_sql_test_model_names(self, *, known_model_names: set[str]) -> set[str]:
        if self._dbt_manifest is None:
            return set()
        names: set[str] = set()
        for model_name, matches in self._dbt_manifest.models_by_name.items():
            if len(matches) == 1:
                if model_name in known_model_names:
                    raise CompileInputError(
                        f"dbt model fixture '__ref__{model_name}' conflicts with a SQLBuild model",
                        code="C218",
                    )
                names.add(model_name)
        for package_name, name in self._dbt_manifest.models_by_package_and_name:
            qualified_name: str = f"{package_name}__{name}"
            if qualified_name in known_model_names:
                raise CompileInputError(
                    f"dbt model fixture '__ref__{qualified_name}' conflicts with a SQLBuild model",
                    code="C218",
                )
            names.add(qualified_name)
        return names

    def extend_sql_test_source_names(self, *, known_source_names: set[str]) -> set[str]:
        if self._dbt_manifest is None:
            return set()
        names: set[str] = set()
        seen_bare: set[tuple[str, str]] = set()
        duplicate_bare: set[tuple[str, str]] = set()
        for source in self._dbt_manifest.sources_by_unique_id.values():
            key: tuple[str, str] = (source.source_name, source.name)
            if key in seen_bare:
                duplicate_bare.add(key)
            seen_bare.add(key)
        for source in self._dbt_manifest.sources_by_unique_id.values():
            bare_name: str = f"{source.source_name}__{source.name}"
            if bare_name in known_source_names:
                raise CompileInputError(
                    f"dbt source fixture '__source__{bare_name}' conflicts with a SQLBuild source",
                    code="C216",
                )
            if (source.source_name, source.name) not in duplicate_bare:
                names.add(bare_name)
            names.add(f"{source.package_name}__{source.source_name}__{source.name}")
        return names

    def extend_sql_test_seed_names(self, *, known_seed_names: set[str]) -> set[str]:
        if self._dbt_manifest is None:
            return set()
        names: set[str] = set()
        seen_bare: set[str] = set()
        duplicate_bare: set[str] = set()
        for seed in self._dbt_manifest.seeds_by_unique_id.values():
            if seed.name in seen_bare:
                duplicate_bare.add(seed.name)
            seen_bare.add(seed.name)
        for seed in self._dbt_manifest.seeds_by_unique_id.values():
            if seed.name in known_seed_names:
                raise CompileInputError(
                    f"dbt seed fixture '__seed__{seed.name}' conflicts with a SQLBuild seed",
                    code="C217",
                )
            if seed.name not in duplicate_bare:
                names.add(seed.name)
            names.add(f"{seed.package_name}__{seed.name}")
        return names

    def validate_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
        owner_relative_sql_path: Path,
    ) -> None:
        validate_compile_model_reference(
            reference=CompileSqlReference(
                ref_kind=ref_kind,
                ref_name=ref_name,
                ref_package=ref_package,
            ),
            model_relative_path=owner_relative_sql_path,
            dbt_manifest=self._dbt_manifest,
        )

    def resolve_reference(
        self,
        *,
        ref_kind: str,
        ref_name: str,
        ref_package: str | None,
    ) -> str | None:
        return resolve_dbt_reference_relation(
            manifest=self._dbt_manifest,
            ref_kind=ref_kind,
            ref_name=ref_name,
            ref_package=ref_package,
        )
