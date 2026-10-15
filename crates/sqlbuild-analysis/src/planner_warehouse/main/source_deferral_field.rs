//! Resolve a deferral target's database or schema template for one source.

use crate::planner_warehouse::constants::{
    CONTEXT_PLACEHOLDER_OPEN, SOURCE_DEFERRAL_CONTEXT_FIELDS, VARIABLE_PLACEHOLDER_OPEN,
};

/// Substitute `${CTX:field}` with the logical value, then `${var}` through `render_variable`.
pub fn source_deferral_field<E>(
    (target_value, logical_value): (Option<&str>, Option<&str>),
    render_variable: impl FnMut(&str) -> Result<Option<String>, E>,
) -> Result<Option<String>, E> {
    let Some(target_value) = target_value else {
        return Ok(logical_value.map(str::to_owned));
    };
    let contexts = substitute(
        (target_value, CONTEXT_PLACEHOLDER_OPEN, |_| true),
        |key: &str| {
            Ok::<_, E>(
                SOURCE_DEFERRAL_CONTEXT_FIELDS
                    .contains(&key)
                    .then(|| logical_value.unwrap_or_default().to_owned()),
            )
        },
    )?;
    let variables = substitute(
        (&contexts, VARIABLE_PLACEHOLDER_OPEN, |name| {
            !name.contains(':')
        }),
        render_variable,
    )?;
    Ok(Some(variables))
}

fn substitute<E>(
    (text, open, accepts): (&str, &str, fn(&str) -> bool),
    mut replace: impl FnMut(&str) -> Result<Option<String>, E>,
) -> Result<String, E> {
    let mut output = String::new();
    let mut position = 0;
    while let Some(found) = text[position..].find(open) {
        let start = position + found;
        let body_start = start + open.len();
        match text[body_start..].find('}') {
            Some(length) if length > 0 && accepts(&text[body_start..body_start + length]) => {
                let key = &text[body_start..body_start + length];
                output.push_str(&text[position..start]);
                let end = body_start + length + 1;
                match replace(key)? {
                    Some(value) => output.push_str(&value),
                    None => output.push_str(&text[start..end]),
                }
                position = end;
            }
            _ => {
                let next = start + open.chars().next().map_or(1, char::len_utf8);
                output.push_str(&text[position..next]);
                position = next;
            }
        }
    }
    output.push_str(&text[position..]);
    Ok(output)
}
