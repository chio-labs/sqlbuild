//! Adapter lexical rules sent with native model rendering requests.

use crate::sql_scan::models::LexicalSyntax;

pub(crate) fn parse_lexical_syntax(syntax_json: &str) -> Result<LexicalSyntax, String> {
    serde_json::from_str(syntax_json).map_err(|error| error.to_string())
}
