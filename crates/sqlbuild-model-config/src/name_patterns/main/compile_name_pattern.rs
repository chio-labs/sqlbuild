//! Compile a dynamic column family's `name_pattern` to match whole column names.

use crate::name_patterns::constants::{
    FULL_MATCH_PREFIX, FULL_MATCH_SUFFIX, SYNTAX_ERROR_PREFIX, TOO_LARGE_MESSAGE,
};
use crate::name_patterns::models::NamePattern;
use regex::Regex;

/// The whole-name matcher for `pattern`, or a one-line reason it is invalid or unsupported.
pub fn compile_name_pattern(pattern: &str) -> Result<NamePattern, String> {
    let compiled = Regex::new(&format!("{FULL_MATCH_PREFIX}{pattern}{FULL_MATCH_SUFFIX}"));
    compiled
        .map(|regex| NamePattern { regex })
        .map_err(|error| match error {
            regex::Error::Syntax(detail) => detail
                .lines()
                .find_map(|line| line.strip_prefix(SYNTAX_ERROR_PREFIX))
                .unwrap_or(detail.as_str())
                .to_owned(),
            _ => TOO_LARGE_MESSAGE.to_owned(),
        })
}
