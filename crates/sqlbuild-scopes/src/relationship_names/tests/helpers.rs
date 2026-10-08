use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::main::expected_model_names::expected_model_names;
use crate::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use crate::relationship_names::models::{ExpectedNames, RelationshipSource, TopLevelCtes};
use crate::relationship_names::tests::test_types::SyntaxTestCase;

const TEST_FILE: &str = "tests/unit/test_orders.sql";
const SCENARIO_FILE: &str = "tests/scenarios/orders.sql";

/// The generic lexical rules of the base adapter.
pub(super) fn generic_syntax() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_owned()],
        ..LexicalSyntax::default()
    }
}

/// The lexical rules one dialect case declares.
pub(super) fn dialect_syntax(test_case: &SyntaxTestCase) -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: owned(test_case.backslash_escape_quotes),
        nested_block_comments: test_case.nested_block_comments,
        line_comment_prefixes: owned(test_case.line_comment_prefixes),
        ..LexicalSyntax::default()
    }
}

/// The native outcome for one SQL test body.
pub(super) fn names(sql: &str, syntax: &LexicalSyntax) -> ExpectedNames {
    expected_model_names(
        &[(sql.to_owned(), TEST_FILE.to_owned())],
        RelationshipSource::Test,
        syntax,
    )
    .remove(0)
}

/// The native outcome for one scenario body.
pub(super) fn scenario_names(sql: &str) -> ExpectedNames {
    expected_model_names(
        &[(sql.to_owned(), SCENARIO_FILE.to_owned())],
        RelationshipSource::Scenario,
        &generic_syntax(),
    )
    .remove(0)
}

/// The top-level CTEs of one SQL test body.
pub(super) fn ctes(sql: &str) -> TopLevelCtes {
    scan_top_level_ctes(sql, TEST_FILE, RelationshipSource::Test, &generic_syntax())
}

/// Expected-model names a case expects the scan to return.
pub(super) fn scanned(names: &[&str]) -> ExpectedNames {
    ExpectedNames::Scanned(owned(names))
}

/// The error a case expects Python to raise.
pub(super) fn failed(message: &str) -> ExpectedNames {
    ExpectedNames::Failed(message.to_owned())
}

/// The CTE names and bodies a scan case expects.
pub(super) fn scanned_ctes(ctes: &[(&str, &str)]) -> TopLevelCtes {
    TopLevelCtes::Scanned(
        ctes.iter()
            .map(|(name, body)| ((*name).to_owned(), (*body).to_owned()))
            .collect(),
    )
}

fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}
