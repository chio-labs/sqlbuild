//! Lexical syntax shared by the code scanner tests.

use crate::sql_scan::models::LexicalSyntax;

pub(crate) fn dialect() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_string(), "#".to_string()],
        nested_block_comments: true,
        ..LexicalSyntax::default()
    }
}
