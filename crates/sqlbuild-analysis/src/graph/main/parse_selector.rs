use crate::graph::errors::SelectorError;
use crate::graph::models::ParsedSelector;

/// Python's `parse_selector` for one token.
pub fn parse_selector(raw: &str) -> Result<ParsedSelector, SelectorError> {
    crate::graph::_helpers::selectors::parse(raw)
}
