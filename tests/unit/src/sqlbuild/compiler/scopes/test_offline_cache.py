"""Offline construction and persistent scope-index cache behavior."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.scopes._helpers.cache import scope_index_fingerprint
from sqlbuild.compiler.scopes.constants import SCOPE_CACHE_DIRECTORY, SCOPE_CACHE_FILENAME
from sqlbuild.compiler.scopes.main.load_or_build_scope_index import load_or_build_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.scopes.types import ResourceKind, ScopeDiagnosticCode
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
    CacheFaultCase,
    FingerprintMutationCase,
    OfflineScopeCase,
    TolerantCategoryCase,
    TolerantMacroInventoryCase,
)
from tests.unit.src.sqlbuild.compiler.scopes.helpers import (
    SCOPE_CACHE_MODEL,
    SCOPE_CACHE_PROJECT,
    write_malformed_payload_cache,
    write_non_text_cache,
    write_oversize_cache,
    write_scope_cache_project,
    write_wrong_digest_cache,
    write_wrong_fingerprint_cache,
    write_wrong_version_cache,
)

_PROJECT: str = SCOPE_CACHE_PROJECT
_MODEL: str = SCOPE_CACHE_MODEL


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("cold write and warm exact reconstruction"),),
    ids=lambda case: case.description,
)
def test_given_valid_project_when_loading_twice_then_warm_cache_reconstructs_exact_index(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)

    cold: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    cache_path: Path = tmp_path / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME
    first_bytes: bytes = cache_path.read_bytes()
    warm: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)

    assert (cold == warm and cold.completeness.complete) is test_case.expected_result
    assert cache_path.read_bytes() == first_bytes


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("warm hit skips authored macro side effect"),),
    ids=lambda case: case.description,
)
def test_given_macro_side_effect_when_loading_warm_cache_then_module_is_not_executed(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/orders.sql": _MODEL,
            "macros/side_effect.py": (
                "from pathlib import Path\n"
                "Path(__file__).with_name('executed').write_text('yes')\n"
                "def identity(value):\n    return str(value)\n"
            ),
        },
    )
    marker: Path = tmp_path / "macros" / "executed"

    load_or_build_scope_index(project_dir=tmp_path)
    marker.unlink()
    load_or_build_scope_index(project_dir=tmp_path)

    assert (not marker.exists()) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("no cache bypasses reads and writes"),),
    ids=lambda case: case.description,
)
def test_given_no_cache_when_loading_twice_then_cache_is_bypassed(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)

    first: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    second: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)

    assert (first == second and not (tmp_path / SCOPE_CACHE_DIRECTORY).exists()) is (
        test_case.expected_result
    )


@pytest.mark.parametrize(
    "test_case",
    (
        FingerprintMutationCase(
            "model content", "models/orders.sql", _MODEL, "MODEL();\nSELECT 2 AS id\n", True
        ),
        FingerprintMutationCase(
            "declaration rendering",
            "sqlbuild_project.toml",
            _PROJECT + '\n[constants]\ncollection_rendering = "value_list"\n',
            _PROJECT + '\n[constants]\ncollection_rendering = "array"\n',
            True,
        ),
        FingerprintMutationCase(
            "connection secret",
            "sqlbuild_project.toml",
            _PROJECT + '\n[connection]\npassword = "first"\n',
            _PROJECT + '\n[connection]\npassword = "second"\n',
            False,
        ),
        FingerprintMutationCase(
            "local target selection",
            "sqlbuild_local.toml",
            'target = "dev"\n[connection]\npassword = "first"\n',
            'target = "prod"\n[connection]\npassword = "second"\n',
            True,
        ),
        FingerprintMutationCase(
            "local connection secret",
            "sqlbuild_local.toml",
            'target = "dev"\n[connection]\npassword = "first"\n',
            'target = "dev"\n[connection]\npassword = "second"\n',
            False,
        ),
        FingerprintMutationCase(
            "project vars",
            "sqlbuild_project.toml",
            _PROJECT + '\n[vars]\nscope_value = "first"\n',
            _PROJECT + '\n[vars]\nscope_value = "second"\n',
            True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_project_mutation_when_fingerprinting_then_only_scope_inputs_invalidate(
    test_case: FingerprintMutationCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)
    path: Path = tmp_path / test_case.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(test_case.initial, encoding="utf-8")
    before: str = scope_index_fingerprint(project_dir=tmp_path)

    path.write_text(test_case.updated, encoding="utf-8")
    after: str = scope_index_fingerprint(project_dir=tmp_path)

    assert (before != after) is test_case.expected_changes_fingerprint


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("identical projects under different absolute roots"),),
    ids=lambda case: case.description,
)
def test_given_same_project_at_different_roots_when_fingerprinting_then_digest_matches(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    first: Path = tmp_path / "first"
    second: Path = tmp_path / "second"
    write_scope_cache_project(root=first, write_repo_files=write_repo_files)
    write_scope_cache_project(root=second, write_repo_files=write_repo_files)

    matches: bool = scope_index_fingerprint(project_dir=first) == scope_index_fingerprint(
        project_dir=second
    )

    assert matches is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("source add rename and delete change canonical paths"),),
    ids=lambda case: case.description,
)
def test_given_source_add_rename_and_delete_when_fingerprinting_then_paths_invalidate(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)
    original: str = scope_index_fingerprint(project_dir=tmp_path)
    added_path: Path = tmp_path / "models" / "added.sql"
    added_path.write_text(_MODEL, encoding="utf-8")
    added: str = scope_index_fingerprint(project_dir=tmp_path)
    renamed_path: Path = tmp_path / "models" / "renamed.sql"
    added_path.rename(renamed_path)
    renamed: str = scope_index_fingerprint(project_dir=tmp_path)
    renamed_path.unlink()
    restored: str = scope_index_fingerprint(project_dir=tmp_path)

    result: bool = len({original, added, renamed}) == 3 and restored == original
    assert result is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("cache excludes authored values secrets and absolute roots"),),
    ids=lambda case: case.description,
)
def test_given_authored_values_and_secrets_when_caching_then_payload_is_value_free(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    secret: str = "super-secret-authored-value"
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT + f'\n[connection]\npassword = "{secret}"\n',
            "models/orders.sql": _MODEL,
            "constants/private.sql": f'CONSTANT (name token, value "{secret}");',
            "enums/private.sql": f'ENUM (name status, members (SECRET "{secret}"));',
        },
    )

    load_or_build_scope_index(project_dir=tmp_path)
    raw: str = (tmp_path / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME).read_text(encoding="ascii")

    assert (secret not in raw and str(tmp_path) not in raw) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("target switch preserves static Python macro dependencies"),),
    ids=lambda case: case.description,
)
def test_given_target_aware_python_composition_when_switching_target_then_dependencies_are_static(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": (
                _PROJECT + '\ndefault_target = "dev"\n[targets.dev]\n[targets.prod]\n'
            ),
            "sqlbuild_local.toml": 'target = "dev"\n',
            "models/orders.sql": "MODEL();\nSELECT @choose() AS value\n",
            "macros/choose.py": (
                "from macros.dev import dev_macro\n"
                "from macros.prod import prod_macro\n\n"
                "def choose(ctx):\n    return dev_macro() "
                'if ctx.target_name == "dev" else prod_macro()\n'
            ),
            "macros/dev.py": 'def dev_macro():\n    return "1"\n',
            "macros/prod.py": 'def prod_macro():\n    return "2"\n',
        },
    )

    dev: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    (tmp_path / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    dev_names: set[str] = {usage.declaration.name for usage in dev.usages}
    prod_names: set[str] = {usage.declaration.name for usage in prod.usages}

    assert (
        {"choose", "dev_macro", "prod_macro"}.issubset(dev_names)
        and {"choose", "dev_macro", "prod_macro"}.issubset(prod_names)
    ) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("broken enum tree retains constant and macro facts"),),
    ids=lambda case: case.description,
)
def test_given_broken_declaration_category_when_loading_then_other_categories_remain_visible(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/orders.sql": _MODEL,
            "models/domain/enums/_enums/broken.sql": (
                "ENUM (name broken, members [BROKEN]);"
            ),
            "constants/limit.sql": "CONSTANT (name limit, value 1);",
            "macros/identity.py": 'def identity():\n    return "1"\n',
        },
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    identities: set[str] = {record.identity.name for record in index.declarations}

    assert ({"limit", "identity"} <= identities and not index.completeness.discovery) is (
        test_case.expected_result
    )


@pytest.mark.parametrize(
    "test_case",
    (
        TolerantMacroInventoryCase(
            description="syntax error retains valid composed macro and dependency",
            files={
                "macros/shared.py": "def shared():\n    return 'shared'\n",
                "macros/consumer.py": (
                    "from macros.shared import shared\n\ndef consumer():\n    return shared()\n"
                ),
                "macros/broken.py": "def broken(:\n    return 'broken'\n",
            },
            expected_names=frozenset({"shared", "consumer"}),
            unexpected_names=frozenset({"broken"}),
            expected_dependencies=(("consumer", "shared"),),
            expected_diagnostic_fragments=("Failed to parse macros",),
        ),
        TolerantMacroInventoryCase(
            description="scope-invalid macro import is omitted with diagnostic",
            files={
                "models/sales/_macros/shared.py": ("def shared():\n    return 'shared'\n"),
                "models/finance/macros/consumer.py": (
                    "from models.sales._macros.shared import shared\n\n"
                    "def consumer():\n    return shared()\n"
                ),
                "macros/broken.py": "def broken(:\n    return 'broken'\n",
            },
            expected_names=frozenset({"shared"}),
            unexpected_names=frozenset({"consumer", "broken"}),
            expected_diagnostic_fragments=("not visible from the importer scope",),
        ),
        TolerantMacroInventoryCase(
            description="name collision retains unrelated valid macro",
            files={
                "macros/valid.py": "def valid():\n    return 'valid'\n",
                "macros/first.py": "def duplicate():\n    return 'first'\n",
                "macros/second.py": "def duplicate():\n    return 'second'\n",
            },
            expected_names=frozenset({"valid"}),
            unexpected_names=frozenset({"duplicate"}),
            expected_diagnostic_fragments=("Macro name collision for 'duplicate'",),
        ),
        TolerantMacroInventoryCase(
            description="import cycle retains unrelated valid macro",
            files={
                "macros/valid.py": "def valid():\n    return 'valid'\n",
                "macros/first.py": (
                    "from macros.second import second\n\ndef first():\n    return second()\n"
                ),
                "macros/second.py": (
                    "from macros.first import first\n\ndef second():\n    return first()\n"
                ),
            },
            expected_names=frozenset({"valid"}),
            unexpected_names=frozenset({"first", "second"}),
            expected_diagnostic_fragments=("Macro import cycle",),
        ),
        TolerantMacroInventoryCase(
            description="module path collision omits both ambiguous modules",
            files={
                "macros/valid.py": "def valid():\n    return 'valid'\n",
                "macros/a.b.py": "def dotted():\n    return 'dotted'\n",
                "macros/a/b.py": "def nested():\n    return 'nested'\n",
            },
            expected_names=frozenset({"valid"}),
            unexpected_names=frozenset({"dotted", "nested"}),
            expected_diagnostic_fragments=("Macro module path collision for 'macros.a.b'",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_macro_fault_when_loading_offline_then_valid_macro_facts_are_retained(
    test_case: TolerantMacroInventoryCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/orders.sql": _MODEL,
            **test_case.files,
        },
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    identities: set[str] = {record.identity.name for record in index.declarations}
    dependencies: tuple[tuple[str, str], ...] = tuple(
        (usage.consumer.name, usage.declaration.name) for usage in index.usages
    )
    diagnostics: str = "\n".join(item.message for item in index.diagnostics)

    assert test_case.expected_names <= identities
    assert not test_case.unexpected_names.intersection(identities)
    assert dependencies == test_case.expected_dependencies
    assert all(fragment in diagnostics for fragment in test_case.expected_diagnostic_fragments)
    assert not index.completeness.discovery


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("non-text corrupt cache is atomically repaired"),),
    ids=lambda case: case.description,
)
def test_given_corrupt_cache_when_loading_then_it_is_a_miss_and_is_atomically_repaired(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)
    expected: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    cache_path: Path = tmp_path / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME
    cache_path.write_bytes(b"\xffnot-json")

    actual: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    repaired: object = json.loads(cache_path.read_text(encoding="ascii"))

    result: bool = actual == expected and isinstance(repaired, dict)
    assert result is test_case.expected_result
    assert not tuple(cache_path.parent.glob(".scope-index-*"))


@pytest.mark.parametrize(
    "test_case",
    (
        CacheFaultCase("wrong version", write_wrong_version_cache),
        CacheFaultCase("wrong fingerprint", write_wrong_fingerprint_cache),
        CacheFaultCase("wrong digest", write_wrong_digest_cache),
        CacheFaultCase("malformed payload", write_malformed_payload_cache),
        CacheFaultCase("oversize", write_oversize_cache),
        CacheFaultCase("non text", write_non_text_cache),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_cache_envelope_when_loading_then_fault_is_a_repairable_miss(
    test_case: CacheFaultCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_scope_cache_project(root=tmp_path, write_repo_files=write_repo_files)
    expected: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    cache_path: Path = tmp_path / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME
    test_case.mutate(path=cache_path)

    actual: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    repaired: dict[str, object] = cast(
        dict[str, object], json.loads(cache_path.read_text(encoding="ascii"))
    )

    assert actual == expected
    assert repaired["schema_version"] == test_case.expected_schema_version


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("placement invalid project returns complete diagnostics"),),
    ids=lambda case: case.description,
)
def test_given_placement_invalid_project_when_loading_then_complete_diagnostics_are_returned(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/domain/constants/value.sql": "CONSTANT (name value, value 1);",
            "models/domain/orders.sql": 'MODEL ();\nSELECT @const("value") AS value',
        },
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    result: bool = index.completeness.complete and any(
        item.code is ScopeDiagnosticCode.OVER_BROAD_INHERITED for item in index.diagnostics
    )

    assert result is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("broken model retains valid and prospective model paths"),),
    ids=lambda case: case.description,
)
def test_given_one_broken_model_when_loading_then_valid_and_broken_paths_remain_queryable(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/valid.sql": _MODEL,
            "models/broken.sql": "MODEL(\nSELECT 1",
            "enums/status.sql": "ENUM status (OPEN = 'open');",
        },
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    paths: set[tuple[ResourceKind, str]] = {
        (item.identity.kind, item.path) for item in index.resources
    }
    result: bool = (
        not index.completeness.discovery
        and not index.completeness.runtime_usage
        and paths
        >= {
            (ResourceKind.MODEL, "models/valid.sql"),
            (ResourceKind.MODEL, "models/broken.sql"),
        }
        and any(item.code is ScopeDiagnosticCode.RESOURCE_PARSE_ERROR for item in index.diagnostics)
    )

    assert result is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    (
        TolerantCategoryCase(
            description="SQL functions retain valid siblings",
            files={
                "functions/sql/valid.sql": "FUNCTION (returns INTEGER);\n1",
                "functions/sql/broken.sql": "FUNCTION (\nSELECT 1",
            },
            expected_kind=ResourceKind.FUNCTION,
            expected_paths=("functions/sql/broken.sql", "functions/sql/valid.sql"),
        ),
        TolerantCategoryCase(
            description="SQL hooks retain valid siblings",
            files={
                "hooks/sql/valid.sql": "HOOK ();\nSELECT 1",
                "hooks/sql/broken.sql": "HOOK (\nSELECT 1",
            },
            expected_kind=ResourceKind.HOOK,
            expected_paths=("hooks/sql/broken.sql", "hooks/sql/valid.sql"),
        ),
        TolerantCategoryCase(
            description="audits retain valid siblings",
            files={
                "audits/valid.sql": "AUDIT ();\nSELECT 1",
                "audits/broken.sql": "AUDIT (\nSELECT 1",
            },
            expected_kind=ResourceKind.AUDIT,
            expected_paths=("audits/broken.sql", "audits/valid.sql"),
        ),
        TolerantCategoryCase(
            description="sources retain valid siblings",
            files={
                "sources/valid.yml": "sources:\n  - name: raw_orders\n    table: orders\n",
                "sources/broken.yml": "sources: [\n",
            },
            expected_kind=ResourceKind.SOURCE,
            expected_paths=("sources/broken.yml", "sources/valid.yml"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_broken_authored_file_when_loading_then_valid_category_siblings_are_retained(
    test_case: TolerantCategoryCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {"sqlbuild_project.toml": _PROJECT, "models/orders.sql": _MODEL} | test_case.files,
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path, no_cache=True)
    actual_paths: tuple[str, ...] = tuple(
        sorted(
            record.path
            for record in filter(
                lambda item: item.identity.kind is test_case.expected_kind,
                index.resources,
            )
        )
    )

    assert actual_paths == test_case.expected_paths
    assert all(str(tmp_path) not in diagnostic.message for diagnostic in index.diagnostics)


@pytest.mark.parametrize(
    "test_case",
    (OfflineScopeCase("partial indexes are not persisted"),),
    ids=lambda case: case.description,
)
def test_given_partial_project_when_loading_then_incomplete_index_is_not_cached(
    test_case: OfflineScopeCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            "sqlbuild_project.toml": _PROJECT,
            "models/broken.sql": "MODEL (\nSELECT 1",
        },
    )

    index: ScopeIndex = load_or_build_scope_index(project_dir=tmp_path)
    cache_path: Path = tmp_path / SCOPE_CACHE_DIRECTORY / SCOPE_CACHE_FILENAME

    assert (not index.completeness.complete and not cache_path.exists()) is (
        test_case.expected_result
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
