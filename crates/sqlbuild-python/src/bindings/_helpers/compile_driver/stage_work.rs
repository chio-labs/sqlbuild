//! How often each compile stage ran in this process, for tests that assert stage work.

use std::collections::BTreeMap;

use pyo3::prelude::{Py, PyRefMut, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::{pyclass, pyfunction};

pub(crate) const EXPRESSION_SHAPES: &str = "infer_native_expression_source_shapes";
pub(crate) const EXPRESSION_SHAPE_BATCHES: &str = "expression_shape_batches";
pub(crate) const EXPRESSION_SHAPES_INFERRED: &str = "expression_shapes_inferred";
pub(crate) const COLUMN_LINEAGE: &str = "build_project_column_lineage";
pub(crate) const MODEL_CONTRACTS: &str = "evaluate_model_contracts";
pub(crate) const PROJECT_DISCOVERIES: &str = "discover_project_inputs";
pub(crate) const MODEL_ANALYSIS: &str = "analyze_native_model_sql";
pub(crate) const SEMANTIC_COMPLETION: &str = "complete_semantic_project";
pub(crate) const SQL_TEST_ASSEMBLY: &str = "assemble_native_sql_tests";
pub(crate) const PROMOTION_CONFLICTS: &str = "promotion_conflict_diagnostics";
pub(crate) const PIVOT_PROOFS: &str = "pivot_proofs";
pub(crate) const SESSION_PIVOT_PROOFS: &str = "session_pivot_proofs";
pub(crate) const DECLARATION_SCOPES: &str = "build_declaration_scope";
pub(crate) const LINEAGE_GRAPH_BUILDS: &str = "lineage_graph_builds";
pub(crate) const PROJECT_GRAPHS: &str = "build_project_graph";
pub(crate) const FORMAT_LINT_BATCHES: &str = "format_lint_batches";
pub(crate) const FORMAT_LINT_FILES: &str = "format_lint_files";
pub(crate) const SQL_TEST_ARTIFACT_PLANS: &str = "plan_compiled_sql_test_artifacts";
pub(crate) const SQL_TEST_MODEL_CHAINS: &str = "sql_test_model_chain_names_by_key";
pub(crate) const BACKGROUND_SQL_TEST_PLANS: &str = "background_sql_test_plans";

/// Compile stage runs since the last reset, by stage.
#[pyclass]
#[derive(Debug, Default)]
pub(crate) struct StageWork {
    runs: BTreeMap<&'static str, u64>,
}

static STAGE_WORK: PyOnceLock<Py<StageWork>> = PyOnceLock::new();

fn stage_work(py: Python<'_>) -> PyResult<PyRefMut<'_, StageWork>> {
    Ok(STAGE_WORK
        .get_or_try_init(py, || Py::new(py, StageWork::default()))?
        .bind(py)
        .borrow_mut())
}

/// Add `count` runs of `stage`.
pub(crate) fn count_stage(py: Python<'_>, stage: &'static str, count: u64) -> PyResult<()> {
    *stage_work(py)?.runs.entry(stage).or_default() += count;
    Ok(())
}

/// Report the runs of each compile stage so far, optionally resetting them.
#[pyfunction]
#[pyo3(signature = (*, reset = false))]
pub(crate) fn compile_stage_work_info(
    py: Python<'_>,
    reset: bool,
) -> PyResult<BTreeMap<String, u64>> {
    let mut work = stage_work(py)?;
    let info: BTreeMap<String, u64> = work
        .runs
        .iter()
        .map(|(stage, count)| ((*stage).to_owned(), *count))
        .collect();
    if reset {
        *work = StageWork::default();
    }
    Ok(info)
}
