//! Detect the aliases that suppress an injected cursor-reference alias.

use crate::resolution::_helpers::alias_tokens::skip_space;
use crate::resolution::constants::REF_CLAUSES;

/// Whether the original SQL supplies an alias after this reference.
pub fn ref_alias(sql: &str, start: usize) -> bool {
    let index = skip_space(sql, start);
    let Some(suffix) = sql.get(index..) else {
        return false;
    };
    let leading = |ch: char| ch.is_alphabetic() || matches!(ch, '_' | '[');
    if suffix
        .get(..2)
        .is_some_and(|s| s.eq_ignore_ascii_case("AS"))
    {
        return sql
            .get(skip_space(sql, index + 2)..)
            .and_then(|s| s.chars().next())
            .is_some_and(leading);
    }
    if !suffix.chars().next().is_some_and(leading) {
        return false;
    }
    let token = if let Some(rest) = suffix.strip_prefix('[') {
        let Some(end) = rest.find(']') else {
            return false;
        };
        if end == 0 {
            return false;
        }
        &rest[..end]
    } else {
        let length = suffix
            .bytes()
            .take_while(|ch| ch.is_ascii_alphanumeric() || *ch == b'_')
            .count();
        if length == 0 {
            return false;
        }
        &suffix[..length]
    };
    !REF_CLAUSES.contains(&token.to_uppercase().as_str())
}
