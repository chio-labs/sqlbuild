use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SqlTestFixtureFacts {
    pub mock: bool,
    pub empty_fixture_marker: bool,
}

/// One batch of SQL tests to plan against the project's models and functions.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanBatch {
    pub models: Vec<SqlTestPlanModel>,
    #[serde(default)]
    pub functions: Vec<SqlTestPlanFunction>,
    pub tests: Vec<SqlTestPlanTest>,
    #[serde(default = "crate::compiler::_helpers::sql_tests::glue::default_true")]
    pub sql_analysis_enabled: bool,
    #[serde(default)]
    pub sql_analysis_dialect: Option<String>,
    #[serde(default = "crate::compiler::_helpers::sql_tests::glue::default_set_difference")]
    pub set_difference_operator: String,
    #[serde(default)]
    pub requires_derived_table_aliases: bool,
    #[serde(default = "crate::compiler::_helpers::sql_tests::glue::default_workers")]
    pub workers: usize,
    #[serde(default = "crate::compiler::_helpers::sql_tests::glue::default_true")]
    pub render_sql: bool,
    #[serde(default = "crate::compiler::_helpers::sql_tests::glue::default_true")]
    pub include_plan: bool,
    pub lexical_syntax: LexicalSyntax,
}

/// The tests whose model chains to resolve; chain ordering reads only declared dependencies.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestChainBatch {
    pub models: Vec<SqlTestChainModel>,
    pub tests: Vec<SqlTestPlanTest>,
    pub lexical_syntax: LexicalSyntax,
}

/// One project model's name and the models it depends on.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestChainModel {
    pub name: String,
    #[serde(default)]
    pub model_dependencies: Vec<String>,
}

/// One project model as SQL tests read it: its SQL and the models it depends on.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanModel {
    pub name: String,
    pub query_sql: String,
    #[serde(default)]
    pub model_dependencies: Vec<String>,
}

/// One project function and the adapter's call templates around its arguments.
#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanFunction {
    pub name: String,
    #[serde(default)]
    pub udf_prefix: Option<String>,
    #[serde(default)]
    pub udf_suffix: Option<String>,
    #[serde(default)]
    pub table_function_prefix: Option<String>,
    #[serde(default)]
    pub table_function_suffix: Option<String>,
}

/// One compiled SQL test to plan.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanTest {
    pub name: String,
    pub file_label: String,
    pub payload: SqlTestPlanPayload,
}

/// A model-mode test's CTEs and overrides, or a direct-logic test's actual and expected CTEs.
#[derive(Debug, Deserialize)]
#[serde(
    tag = "kind",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
pub enum SqlTestPlanPayload {
    Model {
        #[serde(default)]
        authored_ctes: Vec<SqlTestCte>,
        #[serde(default)]
        model_query_overrides: BTreeMap<String, String>,
        #[serde(default)]
        expected_ctes: Vec<SqlTestCte>,
        #[serde(default)]
        expected_model_names: Vec<String>,
        #[serde(default)]
        assertion_ctes: Vec<SqlTestCte>,
        #[serde(default)]
        read_helper_names: Option<Vec<String>>,
        #[serde(default)]
        reference_target_model_names: Option<Vec<String>>,
    },
    Direct {
        mode: String,
        actual_cte: SqlTestCte,
        expected_cte: SqlTestCte,
        #[serde(default)]
        helper_ctes: Vec<SqlTestCte>,
    },
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestCte {
    pub name: String,
    pub sql_body: String,
}

/// One planned SQL test: the executable chain and assertion steps plus optional rendered SQL.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlan {
    pub sql: Option<String>,
    pub chain: Vec<SqlTestChainStep>,
    pub assertions: Vec<SqlTestAssertionStep>,
    pub model_names: Vec<String>,
    pub warnings: Vec<SqlTestPlanWarning>,
}

/// Every planned test in request order, with the batch's wall time split by phase.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanBatchOutcome {
    #[serde(rename = "artifacts")]
    pub plans: Vec<SqlTestPlan>,
    pub planning_ns: u64,
    pub rendering_ns: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestPlanWarning {
    pub model_name: Option<String>,
    pub severity: &'static str,
    pub message: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestChainStep {
    pub model_name: String,
    pub resolved_sql: String,
    #[serde(default)]
    pub expected_cte_sql: Option<String>,
    #[serde(default)]
    pub expected_lifted_ctes: Vec<(String, String)>,
    #[serde(default)]
    pub lifted_ctes: Vec<(String, String)>,
    #[serde(default)]
    pub comparison_body_sql: Option<String>,
    #[serde(default)]
    pub expected_columns: Option<Vec<String>>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SqlTestAssertionStep {
    pub name: String,
    pub resolved_sql: String,
    #[serde(default)]
    pub lifted_ctes: Vec<(String, String)>,
    #[serde(default)]
    pub comparison_body_sql: Option<String>,
}

/// The compiled SQL tests to assemble, with the facts of every model the project compiles.
#[derive(Debug)]
pub struct SqlTestAssemblyBatch {
    pub models: Vec<SqlTestAssemblyModel>,
    pub tests: Vec<SqlTestAssemblyTest>,
    pub lexical_syntax: LexicalSyntax,
}

/// What assembly reads of one model: its name, macro dependencies and references.
#[derive(Debug)]
pub struct SqlTestAssemblyModel {
    pub name: String,
    pub macro_deps: Vec<String>,
    /// The pre-macro SQL to scan for calls when no macro dependencies were recorded and it
    /// contains a macro token; Python scans it only then.
    pub unscanned_macro_source: Option<String>,
    pub references: Vec<SqlTestAssemblyReference>,
}

/// One logical reference: Python `SqlReferenceKind` value, name and optional package.
#[derive(Clone, Debug)]
pub struct SqlTestAssemblyReference {
    pub kind: String,
    pub name: String,
    pub package: Option<String>,
}

/// One expanded SQL test case as compile inputs carry it.
#[derive(Debug)]
pub struct SqlTestAssemblyTest {
    pub block_name: Option<String>,
    pub file_stem: String,
    pub relative_path: String,
    pub relative_stem: String,
    pub contents: String,
    pub block_sql: String,
    pub block_index: i64,
    pub sql_body: String,
    pub case_name: Option<String>,
    /// `(name, value kind, nullable)` per declared parameter.
    pub parameter_schema: Vec<(String, String, bool)>,
    pub parameter_values: Vec<(String, SqlTestParameterValue)>,
    pub payload: SqlTestAssemblyPayload,
}

/// A typed SQL value as its kind and payload; decimals keep their unnormalized digits.
#[derive(Clone, Debug)]
pub enum SqlTestParameterValue {
    String(String),
    Integer(i64),
    Boolean(bool),
    Float(f64),
    Decimal {
        negative: bool,
        digits: Vec<u8>,
        exponent: i64,
    },
    Null,
    List(Vec<SqlTestParameterValue>),
    Set(Vec<SqlTestParameterValue>),
    Object(Vec<(String, SqlTestParameterValue)>),
}

/// The part of a test's payload assembly reads.
#[derive(Debug)]
pub enum SqlTestAssemblyPayload {
    /// A macro, UDF or table-function test of the named resources.
    Direct {
        mode: String,
        tested_resource_names: Vec<String>,
    },
    Model(SqlTestAssemblyModelPayload),
}

#[derive(Debug)]
pub struct SqlTestAssemblyModelPayload {
    pub authored_ctes: Vec<SqlTestCte>,
    pub expected_ctes: Vec<SqlTestCte>,
    pub assertion_ctes: Vec<SqlTestCte>,
    pub expected_model_names: Vec<String>,
    pub assertion_target_model_names: Vec<String>,
    pub reference_target_model_names: Vec<String>,
    pub mock_model_names: Vec<String>,
    pub has_macro_mocks: bool,
}

/// One test's assembled facts, or why Python assembles it.
#[derive(Debug, PartialEq)]
pub enum SqlTestAssemblyOutcome {
    Assembled(AssembledSqlTestFacts),
    Deferred(SqlTestAssemblyDeferral),
}

/// The facts Python's `_assemble_compiled_sql_test` computes for one test.
#[derive(Debug, PartialEq)]
pub struct AssembledSqlTestFacts {
    pub name: String,
    /// `(resource type, name)` per scope dependency, in Python's order.
    pub scope_deps: Vec<(&'static str, String)>,
    pub target_model_names: Vec<String>,
    pub case_fingerprint: Option<String>,
    /// Resource name of the test's diagnostics: the block name, else the relative path's stem.
    pub diagnostic_resource_name: String,
    pub diagnostics: Vec<SqlTestHelperDiagnostic>,
}

/// One P013 diagnostic for a mock that reads a helper calling a reference.
#[derive(Debug, PartialEq, Eq)]
pub struct SqlTestHelperDiagnostic {
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
    pub message: String,
    pub help: String,
}

/// Why one test is assembled by Python instead.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SqlTestAssemblyDeferral {
    /// Macro mocks re-expand every model, which only Python's macro expansion does.
    MacroMocks,
    /// A model's macro call scan raises in Python or meets text Python classifies by Unicode.
    MacroCallScan,
    /// The reference scan fails or cannot classify the text as Python does.
    ReferenceScan,
    /// Non-ASCII text where Python's case folding or Unicode classes would apply.
    NonAsciiText,
    /// A decimal parameter Python's decimal context would round or clamp.
    DecimalContext,
    /// A parameter value the JSON encoder cannot encode as Python's does.
    UnencodableValue,
    /// A parsed CTE tree too deep, or otherwise unfit, to read as Python's `to_dict` walk does.
    UnreadableTree,
}

impl SqlTestAssemblyDeferral {
    /// The kind recorded for the deferral.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::MacroMocks => "macro_mocks",
            Self::MacroCallScan => "macro_call_scan",
            Self::ReferenceScan => "reference_scan",
            Self::NonAsciiText => "non_ascii_text",
            Self::DecimalContext => "decimal_context",
            Self::UnencodableValue => "unencodable_value",
            Self::UnreadableTree => "unreadable_tree",
        }
    }
}
