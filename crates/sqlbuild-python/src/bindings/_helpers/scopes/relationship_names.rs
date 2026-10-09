//! Expected-model relationship names and top-level CTEs of SQL tests and scenarios, scanned natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::relationship_names::main::expected_model_names::expected_model_names;
use sqlbuild_scopes::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use sqlbuild_scopes::relationship_names::models::{
    ExpectedNames, RelationshipSource, TopLevelCtes,
};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

/// One scan's Python error, or its values; `None` where Python must scan the text itself.
type Scanned<T> = Option<(Option<String>, Vec<T>)>;

fn source(scenario: bool) -> RelationshipSource {
    if scenario {
        RelationshipSource::Scenario
    } else {
        RelationshipSource::Test
    }
}

/// Each `(sql, file label)` body's expected models or Python's error; `None` defers to Python.
#[pyfunction]
fn scope_expected_model_names(
    py: Python<'_>,
    texts: Vec<(String, String)>,
    scenario: bool,
    syntax: LexicalSyntaxInput,
) -> PyResult<Vec<Scanned<String>>> {
    let syntax: LexicalSyntax = syntax.into();
    let outcomes: Vec<ExpectedNames> = py
        .compiler_detach(|| Ok(expected_model_names(&texts, source(scenario), &syntax)))
        .map_err(compiler_error)?;
    Ok(outcomes
        .into_iter()
        .map(|outcome| match outcome {
            ExpectedNames::Scanned(names) => Some((None, names)),
            ExpectedNames::Failed(message) => Some((Some(message), Vec::new())),
            ExpectedNames::Deferred => None,
        })
        .collect())
}

/// Each `(sql, file label)` test body's top-level CTEs or Python's error; `None` defers.
#[pyfunction]
fn scope_test_ctes(
    py: Python<'_>,
    texts: Vec<(String, String)>,
    syntax: LexicalSyntaxInput,
) -> PyResult<Vec<Scanned<(String, String)>>> {
    let syntax: LexicalSyntax = syntax.into();
    let outcomes: Vec<TopLevelCtes> = py
        .compiler_detach(|| {
            Ok(texts
                .iter()
                .map(|(sql, file)| {
                    scan_top_level_ctes(sql, file, RelationshipSource::Test, &syntax)
                })
                .collect())
        })
        .map_err(compiler_error)?;
    Ok(outcomes
        .into_iter()
        .map(|outcome| match outcome {
            TopLevelCtes::Scanned(ctes) => Some((None, ctes)),
            TopLevelCtes::Failed(message) => Some((Some(message), Vec::new())),
            TopLevelCtes::Deferred => None,
        })
        .collect())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_expected_model_names, module)?)?;
    module.add_function(wrap_pyfunction!(scope_test_ctes, module)?)?;
    Ok(())
}
