//! Lexical syntaxes and expected references for reference extraction tests.

use crate::sql_references::models::{ReferenceExtraction, SqlReference};
use crate::sql_scan::models::LexicalSyntax;

pub(crate) fn generic() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn backslash_hash_comments() -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: vec!["'".to_string(), "\"".to_string()],
        triple_quoted_strings: true,
        line_comment_prefixes: vec!["--".to_string(), "#".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn unsupported_comments() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_string(), "%".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn reference(kind: &'static str, name: &str) -> SqlReference {
    SqlReference {
        kind,
        name: name.to_string(),
        package: None,
        call_argument_count: None,
    }
}

pub(crate) fn table_function(name: &str, call_argument_count: usize) -> SqlReference {
    SqlReference {
        call_argument_count: Some(call_argument_count),
        ..reference("table_fn", name)
    }
}

pub(crate) fn dbt_reference(package: &str, name: &str) -> SqlReference {
    SqlReference {
        package: Some(package.to_string()),
        ..reference("dbt_ref", name)
    }
}

pub(crate) fn extracted(references: Vec<SqlReference>) -> ReferenceExtraction {
    ReferenceExtraction::Extracted(references)
}

pub(crate) fn failed(message: &str) -> ReferenceExtraction {
    ReferenceExtraction::Failed(message.to_string())
}
