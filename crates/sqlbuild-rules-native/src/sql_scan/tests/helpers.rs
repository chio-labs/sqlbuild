//! Shared lexical syntaxes for SQL scanning tests.

use crate::sql_scan::models::LexicalSyntax;

pub(crate) fn generic() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn single_quote_backslashes() -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: vec!["'".to_string()],
        line_comment_prefixes: vec!["--".to_string(), "//".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn escape_strings() -> LexicalSyntax {
    LexicalSyntax {
        escape_string_prefix: true,
        nested_block_comments: true,
        ..generic()
    }
}

pub(crate) fn triple_quotes() -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: vec!["'".to_string(), "\"".to_string()],
        triple_quoted_strings: true,
        line_comment_prefixes: vec!["--".to_string(), "#".to_string()],
        ..LexicalSyntax::default()
    }
}

pub(crate) fn raw_strings() -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: vec!["'".to_string()],
        raw_string_prefix: true,
        ..generic()
    }
}
