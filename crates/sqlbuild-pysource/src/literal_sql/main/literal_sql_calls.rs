//! Literal SQL passed to the context's SQL methods inside one function.

use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::Ranged;

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::literal_sql::_helpers::arguments::{context_name, literal_text, sql_argument};
use crate::literal_sql::constants::SQL_METHOD_NAMES;
use crate::literal_sql::models::{FunctionSource, LiteralSql};

/// The context's `query`/`execute_sql` calls with literal SQL, in `ast.walk` order; none when unparsable.
#[must_use]
pub fn literal_sql_calls(source: &FunctionSource<'_>) -> Vec<LiteralSql> {
    let Some(parsed): Option<ParsedSource> =
        parse_cpython_module(source.text, source.python_version)
    else {
        return Vec::new();
    };
    let Some(Stmt::FunctionDef(definition)) = parsed.module.body.first() else {
        return Vec::new();
    };
    let Some(context) = context_name(&definition.parameters) else {
        return Vec::new();
    };
    let mut calls: Vec<LiteralSql> = Vec::new();
    for node in walk_breadth_first(
        parsed
            .module
            .body
            .iter()
            .take(1)
            .map(CpythonNode::Stmt)
            .collect(),
    ) {
        let CpythonNode::Expr(Expr::Call(call)) = node else {
            continue;
        };
        let Expr::Attribute(attribute) = call.func.as_ref() else {
            continue;
        };
        let is_context_method: bool = SQL_METHOD_NAMES.contains(&attribute.attr.as_str())
            && matches!(attribute.value.as_ref(), Expr::Name(name) if name.id.as_str() == context);
        if !is_context_method {
            continue;
        }
        if let Some(sql) =
            sql_argument(call).and_then(|argument| literal_text(argument, source.placeholder))
        {
            let (line, _) = source_position(&parsed.lines, call.range().start());
            calls.push(LiteralSql {
                method: attribute.attr.to_string(),
                sql,
                line: source.start_line + line - 1,
            });
        }
    }
    calls
}
