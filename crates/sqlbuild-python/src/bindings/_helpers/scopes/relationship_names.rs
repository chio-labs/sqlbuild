//! Expected-model relationship names of SQL tests and scenarios, scanned natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::relationship_names::main::expected_model_names::expected_model_names;
use sqlbuild_scopes::relationship_names::models::ExpectedNames;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

/// Return each body's expected-model names, or `None` where Python must extract them.
#[pyfunction]
fn scope_expected_model_names(
    py: Python<'_>,
    sqls: Vec<String>,
    syntax: LexicalSyntaxInput,
) -> PyResult<Vec<Option<Vec<String>>>> {
    let syntax: LexicalSyntax = syntax.into();
    let outcomes: Vec<ExpectedNames> = py
        .compiler_detach(|| Ok(expected_model_names(&sqls, &syntax)))
        .map_err(compiler_error)?;
    Ok(outcomes
        .into_iter()
        .map(|outcome| match outcome {
            ExpectedNames::Scanned(names) => Some(names),
            ExpectedNames::Deferred => None,
        })
        .collect())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_expected_model_names, module)?)?;
    Ok(())
}
