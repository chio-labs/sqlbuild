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
    pub additional: AdditionalQueryFacts,
}

#[derive(Debug, Default)]
pub(crate) struct AdditionalQueryFacts {
    pub bare_unions: Vec<Span>,
    pub duplicate_table_aliases: Vec<Span>,
    pub duplicate_output_aliases: Vec<Span>,
    pub mixed_group_order_references: Vec<Span>,
    pub redundant_else_nulls: Vec<Span>,
    pub parenthesized_distincts: Vec<Span>,
    pub constant_predicates: Vec<Span>,
    pub consecutive_semicolons: Vec<Span>,
    pub redundant_self_aliases: Vec<Span>,
    pub count_one_literals: Vec<Span>,
    pub unstable_row_numbers: Vec<Span>,
    pub null_not_in_predicates: Vec<Span>,
    pub set_arity_mismatches: Vec<Span>,
    pub projected_stars: Vec<Span>,
    pub unaliased_calculations: Vec<Span>,
    pub unused_table_aliases: Vec<Span>,
    pub null_rejected_left_joins: Vec<Span>,
    pub implicit_inner_joins: Vec<Span>,
    pub ambiguous_order_directions: Vec<Span>,
    pub unqualified_multi_source_columns: Vec<Span>,
    pub inconsistent_single_source_qualification: Vec<Span>,
    pub unknown_relation_qualifiers: Vec<Span>,
    pub simple_boolean_cases: Vec<Span>,
    pub nested_else_cases: Vec<Span>,
    pub unused_joined_relations: Vec<Span>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LintRequest {
    pub version: u32,
    pub sql: String,
    pub dialect: String,
    #[serde(default)]
    pub enabled_rules: Option<Vec<String>>,
    #[serde(default)]
    pub ignored_rules: Vec<String>,
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
    pub remediation: &'static str,
    pub start: usize,
    pub end: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fix: Option<LintEdit>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fix_unavailable_reason: Option<&'static str>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct LintEdit {
    pub start: usize,
    pub end: usize,
    pub replacement: String,
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct LintRuleMetadata {
    pub code: &'static str,
    pub message: &'static str,
    pub remediation: &'static str,
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
