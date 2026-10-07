//! Expected-model relationship names of SQL tests and scenarios, scanned natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_scopes::relationship_names::main::expected_model_names::expected_model_names;
use sqlbuild_scopes::relationship_names::models::ExpectedNames;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

/// One adapter's `SqlLexicalSyntax`, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct LexicalSyntaxInput {
    backslash_escape_quotes: Vec<String>,
    escape_string_prefix: bool,
    raw_string_prefix: bool,
    triple_quoted_strings: bool,
    nested_block_comments: bool,
    line_comment_prefixes: Vec<String>,
}

impl From<LexicalSyntaxInput> for LexicalSyntax {
    fn from(input: LexicalSyntaxInput) -> Self {
        Self {
            backslash_escape_quotes: input.backslash_escape_quotes,
            escape_string_prefix: input.escape_string_prefix,
            raw_string_prefix: input.raw_string_prefix,
            triple_quoted_strings: input.triple_quoted_strings,
            nested_block_comments: input.nested_block_comments,
            line_comment_prefixes: input.line_comment_prefixes,
        }
    }
}

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
