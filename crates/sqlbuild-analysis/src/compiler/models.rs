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
