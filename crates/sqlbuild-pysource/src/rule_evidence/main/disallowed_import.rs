//! The first import a custom-rule source makes outside the allowlist, in `ast.walk` order.

use ruff_python_ast::Stmt;
use ruff_text_size::Ranged;

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::rule_evidence::main::allowed_custom_rule_import::allowed_custom_rule_import;
use crate::rule_evidence::models::{DisallowedImport, UnparsedSource};

/// The first disallowed absolute import in breadth-first order, or `UnparsedSource`.
pub fn disallowed_import(
    source: &str,
    python_version: (u8, u8),
) -> Result<Option<DisallowedImport>, UnparsedSource> {
    let parsed: ParsedSource =
        parse_cpython_module(source, python_version).ok_or(UnparsedSource)?;
    let roots: Vec<CpythonNode<'_>> = parsed.module.body.iter().map(CpythonNode::Stmt).collect();
    for node in walk_breadth_first(roots) {
        let (statement, modules): (&Stmt, Vec<&str>) = match node {
            CpythonNode::Stmt(statement @ Stmt::Import(import)) => (
                statement,
                import
                    .names
                    .iter()
                    .map(|alias| alias.name.as_str())
                    .collect(),
            ),
            CpythonNode::Stmt(statement @ Stmt::ImportFrom(import)) if import.level == 0 => (
                statement,
                vec![import.module.as_ref().map_or("", |module| module.as_str())],
            ),
            _ => continue,
        };
        if let Some(module) = modules
            .into_iter()
            .find(|module| !allowed_custom_rule_import(module))
        {
            let (line, _) = source_position(&parsed.lines, statement.start());
            return Ok(Some(DisallowedImport {
                line,
                module: module.to_owned(),
            }));
        }
    }
    Ok(None)
}
