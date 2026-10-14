//! Contract-aware formatting of SQL-test fixture bodies.

use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;
use std::collections::HashMap;

use crate::lint_text::models::{FixtureFormatBlock, FixtureFormatRelation};

/// Format parsed blocks, retaining ambiguous CTE replacements and invalid SQL verbatim.
pub fn format_fixture_blocks(
    source: (&str, &str),
    blocks: &[FixtureFormatBlock],
    relations: &HashMap<String, FixtureFormatRelation>,
    syntax: &LexicalSyntax,
) -> Result<Option<String>, regex::Error> {
    crate::lint_text::_helpers::fixture_blocks::format(source, blocks, relations, syntax)
}
