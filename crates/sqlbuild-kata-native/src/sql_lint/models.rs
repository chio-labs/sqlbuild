use polyglot_sql::tokens::Span;
use serde::{Deserialize, Serialize};

#[derive(Debug, Default)]
pub(crate) struct QueryFacts {
    pub null_comparisons: Vec<Span>,
    pub implicit_cartesian_joins: Vec<Span>,
    pub joins_without_condition: Vec<Span>,
    pub unordered_limits: Vec<Span>,
    pub redundant_distincts: Vec<Span>,
    pub positional_set_stars: Vec<Span>,
    pub unused_cte_names: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LintRequest {
    pub version: u32,
    pub sql: String,
    pub dialect: String,
    #[serde(default)]
    pub enabled_rules: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
pub(crate) struct LintResponse {
    pub version: u32,
    pub diagnostics: Vec<LintDiagnostic>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct LintDiagnostic {
    pub code: &'static str,
    pub message: &'static str,
    pub start: usize,
    pub end: usize,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FormatRequest {
    pub version: u32,
    pub sql: String,
    pub dialect: String,
}

#[derive(Debug, Serialize)]
pub(crate) struct FormatResponse {
    pub version: u32,
    pub sql: String,
    pub changed: bool,
    pub formatted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<&'static str>,
}
