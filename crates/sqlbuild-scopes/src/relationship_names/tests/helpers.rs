use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::relationship_names::main::expected_model_names::expected_model_names;
use crate::relationship_names::models::ExpectedNames;
use crate::relationship_names::tests::test_types::SyntaxTestCase;

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

/// The native outcome for one SQL text.
pub(super) fn names(sql: &str, syntax: &LexicalSyntax) -> ExpectedNames {
    expected_model_names(&[sql.to_owned()], syntax).remove(0)
}

/// The outcome a case expects: its names, or a deferral when it has none.
pub(super) fn expected(names: Option<&[&str]>) -> ExpectedNames {
    names.map_or(ExpectedNames::Deferred, |names| {
        ExpectedNames::Scanned(owned(names))
    })
}

fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}
