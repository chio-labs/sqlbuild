use serde_json::Value;

use crate::sql_scan::models::Unclosed;

pub(crate) struct NativeEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) expected_faults: Value,
}

pub(crate) struct ModelLayerRulesTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_codes: &'static [&'static str],
}

pub(crate) struct GraphRuleTestCase {
    pub(crate) description: &'static str,
    pub(crate) exceptions: Value,
    pub(crate) expected_fault_count: usize,
    pub(crate) expected_message_fragments: &'static [&'static str],
}

pub(crate) struct DynamicPivotEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_faults: Value,
}

pub(crate) struct DeclarationScopeTestCase {
    pub(crate) description: &'static str,
    pub(crate) scope: &'static str,
    pub(crate) path: &'static str,
    pub(crate) expected_fault_count: usize,
}

pub(crate) struct DialectEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) query_sql: &'static str,
    pub(crate) expected_code: &'static str,
}

pub(crate) struct ExplicitOutputTypeTestCase {
    pub(crate) description: &'static str,
    pub(crate) query_sql: &'static str,
    pub(crate) columns: Value,
    pub(crate) contract: &'static str,
    pub(crate) expected_fault_count: usize,
    pub(crate) expected_message_fragment: &'static str,
}

pub(crate) struct ContractNameTypeOptionsTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) expected_fault_codes: &'static [&'static str],
}

pub(crate) struct NumericDecisionTestCase {
    pub(crate) description: &'static str,
    pub(crate) query_sql: &'static str,
    pub(crate) authored_sql: &'static str,
    pub(crate) expected_fault_count: usize,
}

pub(crate) struct TypedContractColumnTestCase {
    pub(crate) description: &'static str,
    pub(crate) contract: &'static str,
    pub(crate) columns: Value,
    pub(crate) expected_fault_count: usize,
    pub(crate) expected_messages: &'static [&'static str],
}

pub(crate) struct NormalizationTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_typed_lambda: &'static str,
    pub(crate) expected_quoted_call: &'static str,
    pub(crate) expected_comment: &'static str,
    pub(crate) expected_table_function: &'static str,
    pub(crate) expected_other_dialect_lambda: &'static str,
}

pub(crate) struct DeepExpressionTestCase {
    pub(crate) description: &'static str,
    pub(crate) depth: usize,
    pub(crate) expected_code: &'static str,
}

pub(crate) struct DomainLayoutTestCase {
    pub(crate) description: &'static str,
    pub(crate) code: &'static str,
    pub(crate) models: Value,
    pub(crate) thresholds: Value,
    pub(crate) layout: Value,
    pub(crate) scope_index: Value,
    pub(crate) expected_codes: &'static [&'static str],
    pub(crate) expected_message_fragments: &'static [&'static str],
    pub(crate) expected_absent_fragments: &'static [&'static str],
}

pub(crate) struct ThresholdEvaluationTestCase {
    pub(crate) description: &'static str,
    pub(crate) config: Value,
    pub(crate) query_sql: &'static str,
    pub(crate) references: Value,
    pub(crate) expected_codes: &'static [&'static str],
}

pub(crate) struct ThresholdFingerprintTestCase {
    pub(crate) description: &'static str,
    pub(crate) base_config: Value,
    pub(crate) overridden_config: Value,
    pub(crate) expected_different: bool,
}

pub(crate) struct ScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) scope: Value,
    pub(crate) expected_complete: bool,
    pub(crate) expected_runtime_usage: bool,
    pub(crate) expected_declaration_count: usize,
    pub(crate) expected_visibility_count: usize,
}

pub(crate) struct MalformedScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) scope: Value,
    pub(crate) expected_rejected: bool,
}

pub(crate) struct MissingScopeFactsTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_complete: bool,
    pub(crate) expected_runtime_usage: bool,
}

pub(crate) struct SqlTestRulesTestCase {
    pub(crate) description: &'static str,
    pub(crate) code: &'static str,
    pub(crate) tests: Value,
    pub(crate) scenarios: Value,
    pub(crate) scope_index: Value,
    pub(crate) config: Value,
    pub(crate) expected_fault_count: usize,
    pub(crate) expected_evaluated_models: usize,
    pub(crate) expected_paths: &'static [&'static str],
}

pub(crate) struct SqlTestRulesCacheTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_first_misses: u64,
    pub(crate) expected_second_hits: u64,
    pub(crate) expected_second_misses: u64,
}

pub(crate) struct EmptyInputTestRuleTestCase {
    pub(crate) description: &'static str,
    pub(crate) test: Value,
    pub(crate) allowed_tests: Value,
    pub(crate) expected_messages: &'static [&'static str],
}

pub(crate) struct EmptyInputMinimumTestsTestCase {
    pub(crate) description: &'static str,
    pub(crate) select: Value,
    pub(crate) tests: Value,
    pub(crate) allowed_tests: Value,
    pub(crate) expected_messages: &'static [&'static str],
}

/// One SQL fragment scanned by every native quote- and comment-aware scanner.
pub(crate) struct SqlScannerTestCase {
    pub(crate) description: &'static str,
    pub(crate) fragment: &'static str,
    pub(crate) expected_compiler_paren: Result<usize, Unclosed>,
    pub(crate) expected_table_function: &'static str,
    pub(crate) expected_table_function_token: &'static str,
    pub(crate) expected_snowflake_exclude: &'static str,
    pub(crate) expected_snowflake_comma: &'static str,
    pub(crate) expected_compact: &'static str,
    pub(crate) expected_snowflake_compact: &'static str,
    /// `None` when SQL lint declines non-ASCII input; `Some("")` when no macro site closes.
    pub(crate) expected_lint_site: Option<&'static str>,
    pub(crate) expected_reference_fast_path: bool,
}
