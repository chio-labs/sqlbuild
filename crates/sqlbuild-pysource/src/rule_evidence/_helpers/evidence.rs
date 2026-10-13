//! Test files under `tests/` and the harness cases each one statically declares for a rule.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use ruff_python_ast::{Expr, ExprCall, Stmt};

use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::models::{CpythonNode, ParsedSource, SourceLines};
use crate::rule_evidence::_helpers::cases::{CaseScope, case_declarations};
use crate::rule_evidence::_helpers::imports::{
    assignments, constructors, imports, is_imported_symbol, keyword, read_source,
};
use crate::rule_evidence::_helpers::owners::{
    is_statically_dead, is_statically_skipped, test_owner,
};
use crate::rule_evidence::_helpers::tree::NodeTree;
use crate::rule_evidence::constants::{
    EVALUATE_RULE, PUBLIC_HARNESS_MODULES, PYTHON_SUFFIX, RULE_KEYWORD, TEST_CASE_KEYWORD,
    TEST_FILE_PREFIX, TEST_FILE_SUFFIX,
};
use crate::rule_evidence::models::{RuleTarget, RuleTestEvidence};
use crate::rule_evidence::types::Imports;

/// Every `*.py` path below `directory`, without following directory links.
pub(crate) fn python_files(directory: &Path) -> Vec<PathBuf> {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return Vec::new();
    };
    let mut found: Vec<PathBuf> = Vec::new();
    for entry in entries.flatten() {
        let path: PathBuf = entry.path();
        if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
            found.extend(python_files(&path));
        }
        if path
            .extension()
            .is_some_and(|suffix| suffix == PYTHON_SUFFIX)
        {
            found.push(path);
        }
    }
    found
}

/// Whether pytest collects the file at `path` by its name.
pub(crate) fn is_test_file(path: &Path) -> bool {
    let name: String = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    name.starts_with(TEST_FILE_PREFIX) || name.ends_with(TEST_FILE_SUFFIX)
}

/// The module facts every harness call in one test file is read against.
struct FileScope<'a, 'b> {
    tree: NodeTree<'a>,
    cases: CaseScope<'a, 'b>,
    harness: Vec<String>,
    lines: &'b SourceLines,
}

/// The cases one harness call declares, if it is a live test's call naming the rule.
fn call_evidence(
    scope: &FileScope<'_, '_>,
    (index, call): (usize, &ExprCall),
    (relative_path, target): (&str, &RuleTarget<'_>),
) -> Vec<RuleTestEvidence> {
    let tree: &NodeTree<'_> = &scope.tree;
    let module_imports: &Imports = scope.cases.imports;
    let Some(owner) = test_owner(tree, index) else {
        return Vec::new();
    };
    if is_statically_dead(tree, index, owner) || is_statically_skipped(tree, owner, module_imports)
    {
        return Vec::new();
    }
    let (Some(rule), Some(case)) = (
        keyword(call, RULE_KEYWORD),
        keyword(call, TEST_CASE_KEYWORD),
    ) else {
        return Vec::new();
    };
    let Some(owner_statement @ Stmt::FunctionDef(function)) = tree.stmt(owner) else {
        return Vec::new();
    };
    if !is_imported_symbol(rule, module_imports, &target.modules, target.check_name) {
        return Vec::new();
    }
    let owner_name: String = format!("{relative_path}:{}", function.name.as_str());
    case_declarations(case, owner_statement, &scope.cases)
        .into_iter()
        .map(|declared| {
            let (line, column) =
                source_position(scope.lines, ruff_text_size::Ranged::start(declared));
            RuleTestEvidence {
                path: relative_path.to_owned(),
                line,
                column: column + 1,
                owner: owner_name.clone(),
            }
        })
        .collect()
}

/// The harness cases the test file at `path` declares for the rule.
pub(crate) fn file_evidence(
    path: &Path,
    (relative_path, target): (&str, &RuleTarget<'_>),
    python_version: (u8, u8),
) -> Vec<RuleTestEvidence> {
    let Some(parsed): Option<ParsedSource> =
        parse_cpython_module(&read_source(path), python_version)
    else {
        return Vec::new();
    };
    let body: &[Stmt] = &parsed.module.body;
    let module_imports: Imports = imports(body);
    let module_assignments: HashMap<&str, &Expr> = assignments(body);
    let module_constructors: HashSet<String> = constructors(body, &module_imports);
    let scope = FileScope {
        tree: NodeTree::new(body),
        cases: CaseScope {
            imports: &module_imports,
            assignments: &module_assignments,
            constructors: &module_constructors,
        },
        harness: PUBLIC_HARNESS_MODULES
            .iter()
            .map(|module| (*module).to_owned())
            .collect(),
        lines: &parsed.lines,
    };
    let mut found: Vec<RuleTestEvidence> = Vec::new();
    for (index, node) in scope.tree.nodes.iter().enumerate() {
        if let CpythonNode::Expr(Expr::Call(call)) = node
            && is_imported_symbol(&call.func, &module_imports, &scope.harness, EVALUATE_RULE)
        {
            found.extend(call_evidence(
                &scope,
                (index, call),
                (relative_path, target),
            ));
        }
    }
    found
}
