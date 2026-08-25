from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.cache import (
    build_analysis_cache_context,
    model_analysis_cache_key,
    write_model_analyses,
)
from sqlbuild.compiler.compile._helpers.assembly import project as assembly_project
from sqlbuild.compiler.compile._helpers.refs import cache as reference_cache
from sqlbuild.compiler.compile.constants import COMPILE_CACHE_DISABLE_ENV_VAR
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompileAnalysisSelection,
    CompiledModel,
    CompiledProject,
    CompileSqlReference,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.references.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    AnalysisCacheTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    compile_project_with_cache,
)

_CACHE_REPO_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "cache_demo"\nadapter = "duckdb"\n',
    "sources/raw.yml": """
sources:
  - name: raw_orders
    expression: "(SELECT 1 AS order_id)"
    columns:
      - name: order_id
        type: INTEGER
        nullable: false
""".strip()
    + "\n",
    "models/orders.sql": """
MODEL ();

SELECT order_id FROM __source("raw_orders")
""".strip()
    + "\n",
}
_SELECTION_REPO_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "selection_demo"\nadapter = "duckdb"\n',
    "models/root.sql": "MODEL ();\n\nSELECT 1 AS id\n",
    "models/middle.sql": 'MODEL ();\n\nSELECT id FROM __ref("root")\n',
    "models/leaf.sql": 'MODEL ();\n\nSELECT id FROM __ref("middle")\n',
    "models/unrelated.sql": "MODEL ();\n\nSELECT 2 AS id\n",
}


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="successful cache hit", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_successful_analysis_when_compiling_again_then_reuses_identical_cached_facts(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    cold_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)
    analyzer: Mock = Mock(
        side_effect=AssertionError("Polyglot analysis must not run on a cache hit")
    )
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    signature_builder: Mock = Mock(
        side_effect=AssertionError("output signatures must not be rebuilt on a cache hit")
    )
    monkeypatch.setattr(assembly_project, "model_analysis_output_signature", signature_builder)
    reference_scanner: Mock = Mock(
        side_effect=AssertionError("SQL references must not be scanned on a cache hit")
    )
    monkeypatch.setattr(reference_cache, "extract_sql_references", reference_scanner)

    warm_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)

    assert warm_project.models == cold_project.models
    assert warm_project.diagnostics == cold_project.diagnostics
    analyzer.assert_not_called()
    signature_builder.assert_not_called()
    reference_scanner.assert_not_called()
    assert len(tuple((tmp_path / "target" / "compile-cache").rglob("*.sqlite3"))) == (
        test_case.expected_count + 1
    )


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="changed SQL cache miss", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_changed_expanded_sql_when_compiling_then_writes_a_new_analysis_object(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    cold_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)
    changed_sql = 'MODEL ();\n\nSELECT order_id + 1 AS order_id FROM __source("raw_orders")\n'
    (tmp_path / "models" / "orders.sql").write_text(changed_sql, encoding="utf-8")
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    changed_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)

    assert changed_project.models[0].query_sql != cold_project.models[0].query_sql
    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="corrupt cache fallback", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_corrupt_analysis_when_compiling_then_reanalyzes_and_repairs_the_entry(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    cold_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)
    cache_path: Path = tmp_path / "target" / "compile-cache" / "v4" / "model-analysis.sqlite3"
    with sqlite3.connect(cache_path) as connection:
        persisted_contents: str = connection.execute(
            "SELECT payload FROM model_analysis"
        ).fetchone()[0]
        corrupt_contents: str = persisted_contents.replace("order_id", "tampered", 1)
        assert corrupt_contents != persisted_contents
        _ = connection.execute(
            "UPDATE model_analysis SET payload = ?",
            (corrupt_contents,),
        )
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    repaired_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)

    with sqlite3.connect(cache_path) as connection:
        repaired_contents: str = connection.execute(
            "SELECT payload FROM model_analysis"
        ).fetchone()[0]
    _digest, _separator, serialized_payload = repaired_contents.partition("\n")
    repaired_payload: dict[str, object] = json.loads(serialized_payload)
    assert repaired_project.models == cold_project.models
    assert repaired_payload["v"] == 4
    assert isinstance(repaired_payload["s"], str)
    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="corrupt reference cache fallback", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_corrupt_reference_cache_when_compiling_then_rescans_and_repairs_the_entry(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    cold_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)
    cache_path: Path = next(
        (tmp_path / "target" / "compile-cache" / "references-v2").glob("*.sqlite3")
    )
    with sqlite3.connect(cache_path) as connection:
        persisted_contents: str = connection.execute(
            "SELECT payload FROM sql_reference"
        ).fetchone()[0]
        corrupt_contents: str = persisted_contents.replace("raw_orders", "tampered", 1)
        assert corrupt_contents != persisted_contents
        _ = connection.execute(
            "UPDATE sql_reference SET payload = ?",
            (corrupt_contents,),
        )
    scanner: Mock = Mock(wraps=reference_cache.extract_sql_references)
    monkeypatch.setattr(reference_cache, "extract_sql_references", scanner)

    repaired_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)

    with sqlite3.connect(cache_path) as connection:
        repaired_contents: str = connection.execute("SELECT payload FROM sql_reference").fetchone()[
            0
        ]
    assert repaired_project.models == cold_project.models
    assert "raw_orders" in repaired_contents
    assert scanner.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="unsuccessful result exclusion", expected_count=0),),
    ids=lambda case: case.description,
)
def test_given_unsuccessful_analysis_when_writing_then_does_not_persist_it(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
) -> None:
    write_model_analyses(
        context=AnalysisCacheContext(root=tmp_path, shared_fingerprint="shared"),
        analyses_by_key={
            "a" * 64: PolyglotAnalysisResult(analysis_succeeded=False),
        },
    )

    assert len(tuple(tmp_path.rglob("*.sqlite3"))) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="semantic cache identities", expected_count=5),),
    ids=lambda case: case.description,
)
def test_given_analysis_inputs_when_building_keys_then_all_semantic_inputs_affect_identity(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
) -> None:
    base_context: AnalysisCacheContext | None = build_analysis_cache_context(
        root=tmp_path,
        inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="duckdb"),
        allow_compact_analysis=False,
    )
    profile_context: AnalysisCacheContext | None = build_analysis_cache_context(
        root=tmp_path,
        inference_profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
        allow_compact_analysis=True,
    )
    assert base_context is not None
    assert profile_context is not None
    reference: CompileSqlReference = CompileSqlReference(
        ref_kind=SqlReferenceKind.SOURCE,
        ref_name="raw_orders",
        call_argument_count=1,
    )
    changed_reference: CompileSqlReference = CompileSqlReference(
        ref_kind=SqlReferenceKind.SOURCE,
        ref_name="raw_customers",
        call_argument_count=1,
    )
    base_key: str = model_analysis_cache_key(
        context=base_context,
        query_sql="SELECT 1",
        references=(reference,),
        placeholders=None,
        column_nullability_by_table={},
        column_types_by_table={},
    )

    changed_keys: tuple[str, ...] = (
        model_analysis_cache_key(
            context=base_context,
            query_sql="SELECT 2",
            references=(reference,),
            placeholders=None,
            column_nullability_by_table={},
            column_types_by_table={},
        ),
        model_analysis_cache_key(
            context=base_context,
            query_sql="SELECT 1",
            references=(changed_reference,),
            placeholders=None,
            column_nullability_by_table={},
            column_types_by_table={},
        ),
        model_analysis_cache_key(
            context=base_context,
            query_sql="SELECT 1",
            references=(reference,),
            placeholders={"value": "1"},
            column_nullability_by_table={},
            column_types_by_table={},
        ),
        model_analysis_cache_key(
            context=base_context,
            query_sql="SELECT 1",
            references=(reference,),
            placeholders=None,
            column_nullability_by_table={"raw_orders": {"order_id": InferredNullability.NON_NULL}},
            column_types_by_table={},
        ),
        model_analysis_cache_key(
            context=profile_context,
            query_sql="SELECT 1",
            references=(reference,),
            placeholders=None,
            column_nullability_by_table={},
            column_types_by_table={},
        ),
    )
    unrelated_schema_key: str = model_analysis_cache_key(
        context=base_context,
        query_sql="SELECT 1",
        references=(reference,),
        placeholders=None,
        column_nullability_by_table={"unrelated": {"order_id": InferredNullability.NON_NULL}},
        column_types_by_table={},
    )

    assert len(changed_keys) == test_case.expected_count
    assert all(changed_key != base_key for changed_key in changed_keys)
    assert unrelated_schema_key == base_key


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="scoped schema invalidation", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_schema_change_when_compiling_then_only_direct_consumers_miss_cache(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            **_SELECTION_REPO_FILES,
            "models/root.sql": "MODEL ();\n\nSELECT CAST(NULL AS INTEGER) AS id\n",
        },
    )
    _ = compile_project_with_cache(project_dir=tmp_path)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    unrelated_path: Path = tmp_path / "models" / "unrelated.sql"
    unrelated_path.write_text(
        unrelated_path.read_text(encoding="utf-8").replace(
            "MODEL ();",
            "MODEL (columns (id (nullable false)));",
            1,
        ),
        encoding="utf-8",
    )

    _ = compile_project_with_cache(project_dir=tmp_path)

    analyzer.assert_not_called()
    root_path: Path = tmp_path / "models" / "root.sql"
    root_path.write_text(
        root_path.read_text(encoding="utf-8").replace(
            "MODEL ();",
            "MODEL (columns (id (nullable false)));",
            1,
        ),
        encoding="utf-8",
    )

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count
    _ = compile_project_with_cache(project_dir=tmp_path)
    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="stable exported signature", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_model_sql_change_with_stable_signature_when_compiling_then_downstream_hits_cache(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _SELECTION_REPO_FILES)
    _ = compile_project_with_cache(project_dir=tmp_path)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    (tmp_path / "models" / "root.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="changed exported signature", expected_count=3),),
    ids=lambda case: case.description,
)
def test_given_model_output_change_when_compiling_then_downstream_closure_misses_cache(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _SELECTION_REPO_FILES)
    _ = compile_project_with_cache(project_dir=tmp_path)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    (tmp_path / "models" / "root.sql").write_text(
        "MODEL ();\n\nSELECT 1 AS id, 2 AS extra\n",
        encoding="utf-8",
    )

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count
    _ = compile_project_with_cache(project_dir=tmp_path)
    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="parallel downstream invalidation", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_changed_output_signature_when_reanalyzing_downstream_then_uses_parallel_workers(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _SELECTION_REPO_FILES)
    _ = compile_project_with_cache(project_dir=tmp_path)
    root_path: Path = tmp_path / "models" / "root.sql"
    original_sql: str = root_path.read_text(encoding="utf-8")
    root_path.write_text("MODEL ();\n\nSELECT 1 AS id, 2 AS extra\n", encoding="utf-8")
    _ = compile_project_with_cache(project_dir=tmp_path)
    barrier: threading.Barrier = threading.Barrier(test_case.expected_count)
    worker_ids: set[int] = set()
    real_analyzer: Callable[..., PolyglotAnalysisResult] = (
        assembly_project.analyze_columns_and_lineage_with_polyglot
    )

    def analyze_with_barrier(
        *,
        query_sql: str,
        references: tuple[CompileSqlReference, ...],
        placeholders: dict[str, str] | None,
        column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None,
        column_types_by_table: dict[str, dict[str, str]] | None,
        inference_profile: ExpressionInferenceProfile | None,
        allow_compact_analysis: bool,
    ) -> PolyglotAnalysisResult:
        worker_ids.add(threading.get_ident())
        _ = barrier.wait(timeout=5)
        return real_analyzer(
            query_sql=query_sql,
            references=references,
            placeholders=placeholders,
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            inference_profile=inference_profile,
            allow_compact_analysis=allow_compact_analysis,
        )

    monkeypatch.setattr(
        assembly_project, "analyze_columns_and_lineage_with_polyglot", analyze_with_barrier
    )
    root_path.write_text(original_sql, encoding="utf-8")

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert len(worker_ids) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="restored exported signature", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_cached_model_signature_is_restored_when_compiling_then_downstream_reanalyzes(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _SELECTION_REPO_FILES)
    _ = compile_project_with_cache(project_dir=tmp_path)
    root_path: Path = tmp_path / "models" / "root.sql"
    original_sql: str = root_path.read_text(encoding="utf-8")
    root_path.write_text("MODEL ();\n\nSELECT 1 AS id, 2 AS extra\n", encoding="utf-8")
    _ = compile_project_with_cache(project_dir=tmp_path)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    root_path.write_text(original_sql, encoding="utf-8")

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="selected upstream change", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_selected_upstream_change_when_compiling_full_project_then_stale_consumer_misses(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            **_SELECTION_REPO_FILES,
            "models/middle.sql": 'MODEL ();\n\nSELECT * FROM __ref("root")\n',
            "models/leaf.sql": 'MODEL ();\n\nSELECT * FROM __ref("middle")\n',
        },
    )
    _ = compile_project_with_cache(project_dir=tmp_path)
    (tmp_path / "models" / "root.sql").write_text(
        "MODEL ();\n\nSELECT 1 AS id, 2 AS extra\n",
        encoding="utf-8",
    )
    _ = compile_project_with_cache(
        project_dir=tmp_path,
        analysis_selection=CompileAnalysisSelection(select=("root",)),
    )
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="selected upstream analysis", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_partial_selection_when_compiling_then_analyzes_only_upstream_closure(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _SELECTION_REPO_FILES)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    project: CompiledProject = compile_project_with_cache(
        project_dir=tmp_path,
        analysis_selection=CompileAnalysisSelection(select=("middle",)),
    )

    inferred_by_name: dict[str, bool] = {
        model.name: model.inferred_columns is not None for model in project.models
    }
    assert analyzer.call_count == test_case.expected_count
    assert inferred_by_name == {
        "leaf": False,
        "middle": True,
        "root": True,
        "unrelated": False,
    }
    full_project: CompiledProject = compile_project_with_cache(project_dir=tmp_path)
    full_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in full_project.models
    }
    selected_models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in project.models
    }
    assert selected_models_by_name["root"] == full_models_by_name["root"]
    assert selected_models_by_name["middle"] == full_models_by_name["middle"]


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="unselected invalid reference", expected_count=0),),
    ids=lambda case: case.description,
)
def test_given_unselected_invalid_reference_when_compiling_then_live_validation_still_fails(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    repo_files: dict[str, str] = _SELECTION_REPO_FILES | {
        "models/unrelated.sql": 'MODEL ();\n\nSELECT id FROM __ref("missing")\n'
    }
    write_repo_files(tmp_path, repo_files)

    with pytest.raises(CompileInputError, match="references unknown model"):
        _ = compile_project_with_cache(
            project_dir=tmp_path,
            analysis_selection=CompileAnalysisSelection(select=("middle",)),
        )

    assert len(tuple((tmp_path / "target").rglob("*.sqlite3"))) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="explicit cache bypass", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_compile_cache_bypass_when_compiling_twice_then_both_runs_analyze_cold(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    monkeypatch.setenv(COMPILE_CACHE_DISABLE_ENV_VAR, "1")
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    _ = compile_project_with_cache(project_dir=tmp_path)
    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count
    assert not tuple((tmp_path / "target").rglob("*.sqlite3"))


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="command cache bypass", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_command_cache_bypass_when_compiling_twice_then_both_runs_analyze_cold(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, _CACHE_REPO_FILES)
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)
    _ = compile_project_with_cache(project_dir=tmp_path, no_cache=True)
    _ = compile_project_with_cache(project_dir=tmp_path, no_cache=True)

    assert analyzer.call_count == test_case.expected_count
    assert not tuple((tmp_path / "target").rglob("*.sqlite3"))


@pytest.mark.parametrize(
    "test_case",
    (AnalysisCacheTestCase(description="target cache bypass", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_target_cache_disabled_when_compiling_twice_then_both_runs_analyze_cold(
    test_case: AnalysisCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        {
            **_CACHE_REPO_FILES,
            "sqlbuild_project.toml": """
name = "cache_demo"
adapter = "duckdb"
default_target = "prod"

[targets.prod]
compile_cache = false
""".strip()
            + "\n",
        },
    )
    analyzer: Mock = Mock(wraps=assembly_project.analyze_columns_and_lineage_with_polyglot)
    monkeypatch.setattr(assembly_project, "analyze_columns_and_lineage_with_polyglot", analyzer)

    _ = compile_project_with_cache(project_dir=tmp_path)
    _ = compile_project_with_cache(project_dir=tmp_path)

    assert analyzer.call_count == test_case.expected_count
    assert not tuple((tmp_path / "target").rglob("*.sqlite3"))
