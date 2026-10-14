//! Preserve source aliases when normalizing derived table factors.

use crate::resolution::_helpers::alias_tokens::{alias_token, skip_space};
use crate::resolution::constants::SOURCE_CLAUSES;

/// Return the consumed alias end and the explicit or generated source alias.
pub fn source_alias(sql: &str, start: usize, source_name: &str) -> (usize, String) {
    let token = alias_token(sql, skip_space(sql, start));
    let token = match token {
        Some((end, token)) if token.eq_ignore_ascii_case("AS") => {
            alias_token(sql, skip_space(sql, end))
        }
        other => other,
    };
    if let Some((end, token)) = token
        && !SOURCE_CLAUSES.contains(&token.to_uppercase().as_str())
    {
        return (end, token.to_owned());
    }
    let mut suffix = String::new();
    for ch in source_name.chars() {
        if ch.is_ascii_alphanumeric() || ch == '_' {
            suffix.push(ch.to_ascii_lowercase());
        } else if !suffix.ends_with('_') {
            suffix.push('_');
        }
    }
    let suffix = suffix.trim_matches('_');
    (
        start,
        format!(
            "__sqb_source_{}",
            if suffix.is_empty() { "source" } else { suffix }
        ),
    )
}
