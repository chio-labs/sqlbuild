//! String constants of a Python module that name a renamed model or column.

use ruff_python_ast::Expr;
use ruff_text_size::{Ranged, TextSize};

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::string_literals::_helpers::flags::flags;
use crate::string_literals::models::StringQuery;

/// The 1-based line and column of each flagged `str` constant in `ast.walk` order; none when unparsable.
#[must_use]
pub fn string_literal_locations(
    contents: &str,
    query: &StringQuery<'_>,
    python_version: (u8, u8),
) -> Vec<(usize, usize)> {
    let Some(parsed): Option<ParsedSource> = parse_cpython_module(contents, python_version) else {
        return Vec::new();
    };
    let mut locations: Vec<(usize, usize)> = Vec::new();
    for node in walk_breadth_first(parsed.module.body.iter().map(CpythonNode::Stmt).collect()) {
        let (value, start): (&str, TextSize) = match &node {
            CpythonNode::Expr(Expr::StringLiteral(literal)) => {
                (literal.value.to_str(), literal.range().start())
            }
            CpythonNode::Text(constant) => (&constant.value, constant.start),
            _ => continue,
        };
        if flags(value, query) {
            let (line, column) = source_position(&parsed.lines, start);
            locations.push((line, column + 1));
        }
    }
    locations
}
