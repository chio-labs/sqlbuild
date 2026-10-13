//! Separate formatter-root paths from model selectors.

use crate::format_command::_helpers::selectors::lint_path_prefixes;
use crate::format_command::constants::{
    LINT_DIRECTORY_NAMES, PATH_SELECTOR_PREFIX, PATH_SEPARATOR, UNKNOWN_ROOT_CODE,
};
use crate::format_command::errors::FormatSelectorError;

fn reject_unknown_root(token: &str) -> Result<(), FormatSelectorError> {
    let normalized: String = token.replace('\\', "/");
    let Some(path) = normalized.strip_prefix(PATH_SELECTOR_PREFIX) else {
        return Ok(());
    };
    let root: &str = path
        .trim_matches(PATH_SEPARATOR)
        .split(PATH_SEPARATOR)
        .next()
        .unwrap_or_default();
    if LINT_DIRECTORY_NAMES.contains(&root) {
        return Ok(());
    }
    let roots: Vec<String> = LINT_DIRECTORY_NAMES
        .iter()
        .map(|name| format!("'{name}/'"))
        .collect();
    Err(FormatSelectorError {
        message: format!(
            "format path selectors must start with one of: {}",
            roots.join(", ")
        ),
        code: UNKNOWN_ROOT_CODE,
        help: None,
    })
}

/// The path prefixes and the model selector tokens, rejecting `path:` outside formatter roots.
pub fn partition_lint_selectors(
    raw_selectors: &[String],
) -> Result<(Vec<String>, Vec<String>), FormatSelectorError> {
    let mut path_tokens: Vec<String> = Vec::new();
    let mut model_tokens: Vec<String> = Vec::new();
    for raw_selector in raw_selectors {
        for token in raw_selector.split_whitespace() {
            reject_unknown_root(token)?;
            match lint_path_prefixes(&[token.to_owned()]) {
                Some(prefixes) => path_tokens.extend(prefixes),
                None => model_tokens.push(token.to_owned()),
            }
        }
    }
    Ok((path_tokens, model_tokens))
}
