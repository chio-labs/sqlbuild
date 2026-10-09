//! Test-only hook comparing native CTE fact recovery with Python's, function for function.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::main::recover_cte_facts::recover_cte_facts;
use sqlbuild_analysis::assembly::analysis_session::models::{CteFactRequest, CteFacts};
use sqlbuild_analysis::assembly::analysis_session::types::{Pairs, Shapes};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::types::CompilerDetach;

/// `(cleaned SQL, dialect, input schemas, return types, nullability rules, recover, null filter)`.
type RecoveryRow = (String, String, Shapes, Pairs, Option<Pairs>, bool, bool);
/// `(deferral, types, nullability, sorted direct outputs, sorted non-null outputs)`.
type FactsRow = (Option<String>, Pairs, Pairs, Vec<String>, Vec<String>);

/// The facts native enrichment recovers for one query, or the reason it defers to Python.
#[pyfunction]
fn _oracle_cte_fact_recovery(py: Python<'_>, request: RecoveryRow) -> PyResult<FactsRow> {
    let (
        cleaned_sql,
        dialect,
        input_schemas,
        function_return_types,
        nullability_rules,
        recover,
        null_filter,
    ) = request;
    let request = CteFactRequest {
        cleaned_sql,
        dialect,
        input_schemas,
        function_return_types,
        nullability_rules,
        recover,
        null_filter,
    };
    let facts: Result<CteFacts, String> = py
        .compiler_detach(|| Ok(recover_cte_facts(&request)))
        .map_err(value_error)?;
    Ok(match facts {
        Ok(facts) => (
            None,
            facts.types,
            facts.nullability,
            facts.direct_outputs,
            facts.non_null_outputs,
        ),
        Err(deferral) => (
            Some(deferral),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ),
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(_oracle_cte_fact_recovery, module)?)?;
    Ok(())
}
