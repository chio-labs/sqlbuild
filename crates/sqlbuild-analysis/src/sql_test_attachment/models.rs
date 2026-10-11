//! The facts and problems the SQL-test attachment checks report.

use crate::compiler::models::SqlTestCteText;
use crate::sql_test_attachment::_helpers::text_matching::{identifier_tokens, reads_word};
use crate::sql_test_attachment::types::SqlTestTextMatcher;

/// A model test's classified CTEs, as the attachment's helper checks read them.
#[derive(Debug, Clone, Copy)]
pub struct ModelTestCtes<'a> {
    pub authored: &'a [SqlTestCteText],
    pub expected: &'a [SqlTestCteText],
    pub assertions: &'a [SqlTestCteText],
    pub mock_models: &'a [String],
    pub mock_sources: &'a [String],
    pub mock_seeds: &'a [String],
    pub mock_dbt_refs: &'a [String],
    pub mock_table_functions: &'a [String],
}

/// `SqlTestReads`: the helpers a test reads and the unmocked models they read.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SqlTestReadFacts {
    pub read_helper_names: Vec<String>,
    pub reference_target_model_names: Vec<String>,
}

/// One P013 problem in a model test, located at `call` inside CTE `cte_name` when given.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SqlTestHelperProblem {
    pub cte_name: String,
    pub call: Option<String>,
    pub message: String,
    pub help: String,
}

/// Why a helper check stopped: an internal failure, a reference scan error, or the matcher's.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SqlTestCheckFailure<E> {
    Internal(String),
    Scan(String),
    Matcher(E),
}

/// A reported span: 1-based start and end lines and columns.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CteLocation {
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

/// Python `re` semantics of the SQL-test text checks for the running Python's Unicode tables.
#[derive(Clone, Copy, Debug, Default)]
pub struct PythonTextMatcher;

impl SqlTestTextMatcher for PythonTextMatcher {
    type Error = std::convert::Infallible;

    fn identifier_tokens(&self, sql: &str) -> Result<Vec<String>, Self::Error> {
        Ok(identifier_tokens(sql))
    }

    fn reads_word(&self, sql: &str, word: &str) -> Result<bool, Self::Error> {
        Ok(reads_word(sql, word))
    }
}
