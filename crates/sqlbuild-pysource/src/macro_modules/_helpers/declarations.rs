//! Top-level declarations of a macro module: private-name rules, exports and their signatures.

use ruff_python_ast::{Expr, ModModule, Stmt, StmtFunctionDef};
use ruff_text_size::Ranged;
use std::collections::HashSet;

use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::CpythonNode;
use crate::macro_modules::constants::PRIVATE_PREFIX;

/// The first public name a non-function top-level statement declares, if any.
pub(crate) fn public_non_function_declaration(statement: &Stmt) -> Option<String> {
    let names: Vec<String> = match statement {
        Stmt::ClassDef(class) => vec![class.name.as_str().to_owned()],
        Stmt::TypeAlias(alias) => match alias.name.as_ref() {
            Expr::Name(name) => vec![name.id.as_str().to_owned()],
            _ => Vec::new(),
        },
        Stmt::Assign(assign) => assign
            .targets
            .iter()
            .flat_map(|target| walk_breadth_first(vec![CpythonNode::Expr(target)]))
            .filter_map(|node| node.name())
            .map(|name| name.id.as_str().to_owned())
            .collect(),
        Stmt::AnnAssign(assign) => match assign.target.as_ref() {
            Expr::Name(name) => vec![name.id.as_str().to_owned()],
            _ => Vec::new(),
        },
        _ => Vec::new(),
    };
    names
        .into_iter()
        .find(|name| !name.starts_with(PRIVATE_PREFIX))
}

/// The top-level function definitions, public or not, in source order.
pub(crate) fn top_level_functions(module: &ModModule) -> impl Iterator<Item = &StmtFunctionDef> {
    module.body.iter().filter_map(|statement| match statement {
        Stmt::FunctionDef(function) => Some(function),
        _ => None,
    })
}

/// Whether a function name is exported.
pub(crate) fn is_public(name: &str) -> bool {
    !name.starts_with(PRIVATE_PREFIX)
}

/// Names of the public top-level functions.
pub(crate) fn module_exports(module: &ModModule) -> HashSet<String> {
    top_level_functions(module)
        .map(|function| function.name.as_str())
        .filter(|name| is_public(name))
        .map(str::to_owned)
        .collect()
}

/// Parameter names in `posonlyargs, args, vararg, kwonlyargs, kwarg` order.
pub(crate) fn parameter_names(function: &StmtFunctionDef) -> Vec<String> {
    let parameters = &function.parameters;
    parameters
        .posonlyargs
        .iter()
        .chain(&parameters.args)
        .map(|parameter| &parameter.parameter)
        .chain(parameters.vararg.as_deref())
        .chain(
            parameters
                .kwonlyargs
                .iter()
                .map(|parameter| &parameter.parameter),
        )
        .chain(parameters.kwarg.as_deref())
        .map(|parameter| parameter.name.as_str().to_owned())
        .collect()
}

/// CPython's `lineno` of a function: the line of its `def`, or of `async` for a coroutine.
pub(crate) fn definition_line(source: &str, function: &StmtFunctionDef) -> usize {
    let mut start: usize = keyword_start(source, function.name.start().to_usize(), "def");
    if function.is_async {
        start = keyword_start(source, start, "async");
    }
    line_number(&source[..start])
}

/// Where `keyword` starts, reading back from `end` over blanks and line continuations.
fn keyword_start(source: &str, end: usize, keyword: &str) -> usize {
    let mut text: &str = &source[..end];
    loop {
        let trimmed: &str = text.trim_end_matches([' ', '\t', '\x0c']);
        let continued: Option<&str> = trimmed
            .strip_suffix("\\\r\n")
            .or_else(|| trimmed.strip_suffix("\\\n"))
            .or_else(|| trimmed.strip_suffix("\\\r"));
        match continued {
            Some(rest) => text = rest,
            None => {
                text = trimmed;
                break;
            }
        }
    }
    text.strip_suffix(keyword).map_or(text.len(), str::len)
}

/// The 1-based line of the text's end, counting `\n`, `\r\n` and `\r` as line breaks.
fn line_number(text: &str) -> usize {
    let bytes: &[u8] = text.as_bytes();
    let mut line: usize = 1;
    for (index, byte) in bytes.iter().enumerate() {
        if *byte == b'\n' || (*byte == b'\r' && bytes.get(index + 1) != Some(&b'\n')) {
            line += 1;
        }
    }
    line
}
