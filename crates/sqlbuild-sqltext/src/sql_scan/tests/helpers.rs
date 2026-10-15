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

/// Lexical rules with the given quotes, `[escape, raw, triple, nested]` flags and prefixes.
pub(crate) fn syntax(quotes: &[&str], flags: [bool; 4], prefixes: &[&str]) -> LexicalSyntax {
    LexicalSyntax {
        backslash_escape_quotes: quotes.iter().map(|quote| (*quote).to_owned()).collect(),
        escape_string_prefix: flags[0],
        raw_string_prefix: flags[1],
        triple_quoted_strings: flags[2],
        nested_block_comments: flags[3],
        line_comment_prefixes: prefixes.iter().map(|prefix| (*prefix).to_owned()).collect(),
    }
}
