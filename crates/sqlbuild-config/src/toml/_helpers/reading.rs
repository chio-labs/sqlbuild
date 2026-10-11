//! Read a TOML document natively, splitting off what the parser cannot nest.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::toml::_helpers::integers::{
    Placeholder, placeholder_mark, restore_placeholders, substitute_placeholders,
};
use crate::toml::constants::SPLIT_VALUE_KEY;

/// The value of one container nested past the parser's limit, read as its own document.
fn deep_value(text: &str, (start, end): (usize, usize)) -> Result<Placeholder, ConfigError> {
    let document = format!("{SPLIT_VALUE_KEY} = {}", &text[start..end]);
    let lines_before = text[..start].matches('\n').count();
    let value = load_document(&document).map_err(|error| ConfigError {
        line: error.line.map(|line| line + lines_before),
        ..error
    })?;
    let restored = value
        .get(SPLIT_VALUE_KEY)
        .cloned()
        .unwrap_or(ConfigValue::Null);
    Ok((start, end, restored))
}

fn is_inside(ranges: &[(usize, usize)], offset: usize) -> bool {
    ranges
        .iter()
        .any(|(start, end)| *start <= offset && offset < *end)
}

/// An upper bound of the bracket nesting of `text`, counting brackets inside strings too.
pub(crate) fn bracket_depth(text: &str) -> usize {
    let mut depth: usize = 0;
    let mut deepest: usize = 0;
    for byte in text.bytes() {
        match byte {
            b'[' | b'{' => {
                depth += 1;
                deepest = deepest.max(depth);
            }
            b']' | b'}' => depth = depth.saturating_sub(1),
            _ => {}
        }
    }
    deepest
}

/// `tomllib.loads` on the current thread.
pub(crate) fn load_document(text: &str) -> Result<ConfigValue, ConfigError> {
    if text.starts_with(BYTE_ORDER_MARK) {
        return Err(ConfigError::new(
            ConfigErrorKind::Syntax,
            "invalid statement: tomllib does not skip a byte order mark",
        ));
    }
    let text = text.replace("\r\n", "\n");
    let (large_integers, deep_ranges) =
        crate::toml::_helpers::version::reject_toml_1_1_syntax(&text)?;
    crate::toml::_helpers::namespaces::reject_namespace_conflicts(&text)?;
    let mut placeholders: Vec<Placeholder> = deep_ranges
        .iter()
        .map(|range| deep_value(&text, *range))
        .collect::<Result<_, _>>()?;
    placeholders.extend(
        large_integers
            .into_iter()
            .filter(|(start, _, _)| !is_inside(&deep_ranges, *start)),
    );
    if placeholders.is_empty() {
        return crate::toml::_helpers::conversion::parse_document(&text);
    }
    placeholders.sort_by_key(|(start, _, _)| *start);
    let mark = placeholder_mark(&text)?;
    let substituted = substitute_placeholders(&text, &placeholders, mark);
    crate::toml::_helpers::conversion::parse_document(&substituted)
        .map(|value| restore_placeholders(value, &placeholders, mark))
}
