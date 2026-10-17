//! Expected-model relationship names and top-level CTEs of SQL tests and scenarios, scanned natively.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::relationship_names::main::expected_model_names::expected_model_names;
use sqlbuild_scopes::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use sqlbuild_scopes::relationship_names::models::{
    ExpectedNames, RelationshipSource, TopLevelCtes,
};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::construct::new_record;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

/// One scan's error, or its values.
type Scanned<T> = (Option<String>, Vec<T>);

fn source(scenario: bool) -> RelationshipSource {
    if scenario {
        RelationshipSource::Scenario
    } else {
        RelationshipSource::Test
    }
}

/// Each `(sql, file label)` body's expected models or the scan's error.
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
            ExpectedNames::Scanned(names) => (None, names),
            ExpectedNames::Failed(message) => (Some(message), Vec::new()),
        })
        .collect())
}

/// Each `(sql, file label)` test body's top-level CTEs or the scan's error.
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
            TopLevelCtes::Scanned(ctes) => (None, ctes),
            TopLevelCtes::Failed(message) => (Some(message), Vec::new()),
        })
        .collect())
}

/// One SQL test body's raw top-level CTEs; a scan failure raises `CompileInputError`.
#[pyfunction]
#[pyo3(signature = (*, sql, file_label, syntax))]
fn extract_sql_test_ctes<'py>(
    py: Python<'py>,
    sql: &str,
    file_label: &str,
    syntax: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let syntax: LexicalSyntax = native_field(syntax, "native_mapping")?
        .extract::<LexicalSyntaxInput>()?
        .into();
    let outcome: TopLevelCtes = py
        .compiler_detach(|| {
            Ok(scan_top_level_ctes(
                sql,
                file_label,
                RelationshipSource::Test,
                &syntax,
            ))
        })
        .map_err(compiler_error)?;
    let ctes: Vec<(String, String)> = match outcome {
        TopLevelCtes::Scanned(ctes) => ctes,
        TopLevelCtes::Failed(message) => {
            let error: Bound<'py, PyAny> =
                error_class(py, ErrorId::CompileInput)?.call1((message,))?;
            return Err(PyErr::from_value(error));
        }
    };
    let mut built: Vec<Bound<'py, PyAny>> = Vec::with_capacity(ctes.len());
    for (name, body) in ctes {
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("name", name)?;
        arguments.set_item("sql_body", body)?;
        built.push(new_record(
            py,
            RecordId::CompileSqlTestCte,
            (),
            Some(&arguments),
        )?);
    }
    PyTuple::new(py, built)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(extract_sql_test_ctes, module)?)?;
    module.add_function(wrap_pyfunction!(scope_expected_model_names, module)?)?;
    module.add_function(wrap_pyfunction!(scope_test_ctes, module)?)?;
    Ok(())
}
