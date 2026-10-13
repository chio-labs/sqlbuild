//! The test function that owns a harness call, and whether that call can ever run.

use ruff_python_ast::{Decorator, Expr, Stmt, StmtFunctionDef};

use crate::cpython_tree::models::CpythonNode;
use crate::rule_evidence::_helpers::imports::{
    constant_truth, is_pytest_mark, is_true_constant, keyword,
};
use crate::rule_evidence::_helpers::tree::NodeTree;
use crate::rule_evidence::constants::{
    CONDITION_KEYWORD, SKIP_MARK, SKIPIF_MARK, TEST_CLASS_PREFIX, TEST_FUNCTION_PREFIX,
};
use crate::rule_evidence::types::Imports;

fn class_index(tree: &NodeTree<'_>, index: Option<usize>) -> Option<usize> {
    let index: usize = index?;
    matches!(tree.stmt(index), Some(Stmt::ClassDef(_))).then_some(index)
}

/// The top-level or `Test*`-class `test_*` function enclosing `node`, unless a lambda or class intervenes.
pub(crate) fn test_owner(tree: &NodeTree<'_>, node: usize) -> Option<usize> {
    let mut current: usize = node;
    while let Some(parent) = tree.parents[current] {
        current = parent;
        if matches!(tree.nodes[current], CpythonNode::Expr(Expr::Lambda(_)))
            || class_index(tree, Some(current)).is_some()
        {
            return None;
        }
        let Some(Stmt::FunctionDef(function)) = tree.stmt(current) else {
            continue;
        };
        if !function.name.as_str().starts_with(TEST_FUNCTION_PREFIX) {
            return None;
        }
        let Some(parent) = tree.parents[current] else {
            return Some(current);
        };
        let Some(Stmt::ClassDef(class)) =
            class_index(tree, Some(parent)).and_then(|class| tree.stmt(class))
        else {
            return None;
        };
        return (class.name.as_str().starts_with(TEST_CLASS_PREFIX)
            && tree.parents[parent].is_none())
        .then_some(current);
    }
    None
}

/// Whether one decorator is `pytest.mark.skip` or an always-true `pytest.mark.skipif`.
fn skips_statically(decorator: &Decorator, imports: &Imports) -> bool {
    let call = match &decorator.expression {
        Expr::Call(call) => Some(call),
        _ => None,
    };
    let target: &Expr = call.map_or(&decorator.expression, |call| &call.func);
    if is_pytest_mark(target, imports, SKIP_MARK) {
        return true;
    }
    let Some(call) = call else {
        return false;
    };
    if !is_pytest_mark(&call.func, imports, SKIPIF_MARK) {
        return false;
    }
    let condition: Option<&Expr> = match call.arguments.args.first() {
        Some(first) => Some(first),
        None => keyword(call, CONDITION_KEYWORD),
    };
    condition.is_some_and(is_true_constant)
}

fn skips(decorators: &[Decorator], imports: &Imports) -> bool {
    decorators
        .iter()
        .any(|decorator| skips_statically(decorator, imports))
}

/// Whether the owner or its enclosing class carries `skip` or an always-true `skipif`.
pub(crate) fn is_statically_skipped(tree: &NodeTree<'_>, owner: usize, imports: &Imports) -> bool {
    let Some(Stmt::FunctionDef(function)) = tree.stmt(owner) else {
        return false;
    };
    let function: &StmtFunctionDef = function;
    if skips(&function.decorator_list, imports) {
        return true;
    }
    match class_index(tree, tree.parents[owner]).and_then(|class| tree.stmt(class)) {
        Some(Stmt::ClassDef(class)) => skips(&class.decorator_list, imports),
        _ => false,
    }
}

/// The test and body of an `If`, an `elif` or a `While` node, when the test is constant.
fn constant_branch<'a>(node: &CpythonNode<'a>) -> Option<(bool, &'a [Stmt])> {
    let (test, body): (&Expr, &[Stmt]) = match node {
        CpythonNode::Stmt(Stmt::If(statement)) => (&statement.test, &statement.body),
        CpythonNode::Stmt(Stmt::While(statement)) => (&statement.test, &statement.body),
        CpythonNode::Elif(clauses) => {
            let clause = clauses.first()?;
            (clause.test.as_ref()?, &clause.body)
        }
        _ => return None,
    };
    Some((constant_truth(test)?, body))
}

/// Whether a constant `if` or `while` test keeps `node` from ever running inside `owner`.
pub(crate) fn is_statically_dead(tree: &NodeTree<'_>, node: usize, owner: usize) -> bool {
    let mut current: usize = node;
    while current != owner {
        let Some(parent) = tree.parents[current] else {
            return true;
        };
        if let Some((truth, body)) = constant_branch(&tree.nodes[parent]) {
            let in_body: bool = tree
                .stmt(current)
                .is_some_and(|statement| body.iter().any(|item| std::ptr::eq(item, statement)));
            if in_body != truth {
                return true;
            }
        }
        current = parent;
    }
    false
}
