//! Macro calls inside top-level function bodies, and names used outside them.

use ruff_python_ast::{Expr, ExprContext, ModModule, StmtFunctionDef};
use std::collections::{HashMap, HashSet};

use crate::cpython_tree::main::child_nodes::child_nodes;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::CpythonNode;

/// The identity of an `ast.Name` node: its address in the parsed tree.
pub(crate) type NodeId = *const Expr;

/// The imported macro bindings and local function names one module's calls resolve against.
pub(crate) struct CallNames<'a> {
    /// Local binding to imported macro name.
    pub(crate) imported: &'a HashMap<String, String>,
    pub(crate) functions: &'a HashSet<String>,
    pub(crate) display: &'a str,
}

/// One function's dependencies on imported macros and the local functions it calls.
pub(crate) struct FunctionCalls {
    pub(crate) dependencies: Vec<String>,
    pub(crate) helpers: Vec<String>,
}

/// The nodes of a function body, depth first, without entering nested scopes.
pub(crate) fn runtime_nodes(function: &StmtFunctionDef) -> Vec<CpythonNode<'_>> {
    let mut nodes: Vec<CpythonNode<'_>> = Vec::new();
    let mut pending: Vec<CpythonNode<'_>> =
        function.body.iter().rev().map(CpythonNode::Stmt).collect();
    while let Some(node) = pending.pop() {
        if !node.opens_scope() {
            pending.extend(child_nodes(&node).into_iter().rev());
        }
        nodes.push(node);
    }
    nodes
}

fn bound_names(function: &StmtFunctionDef, nodes: &[CpythonNode<'_>]) -> HashSet<String> {
    let parameters = &function.parameters;
    let mut names: HashSet<String> = parameters
        .posonlyargs
        .iter()
        .chain(&parameters.args)
        .chain(&parameters.kwonlyargs)
        .map(|parameter| parameter.parameter.name.as_str().to_owned())
        .collect();
    names.extend(
        parameters
            .vararg
            .iter()
            .chain(&parameters.kwarg)
            .map(|parameter| parameter.name.as_str().to_owned()),
    );
    names.extend(
        nodes
            .iter()
            .filter_map(|node| node.name())
            .filter(|name| name.ctx == ExprContext::Store)
            .map(|name| name.id.as_str().to_owned()),
    );
    names
}

fn first_sorted<'a>(names: impl Iterator<Item = &'a String>) -> Option<&'a String> {
    names.min()
}

fn direct_call_name<'a>(node: &CpythonNode<'a>) -> Option<&'a Expr> {
    match node {
        CpythonNode::Expr(Expr::Call(call)) if call.func.is_name_expr() => Some(&call.func),
        _ => None,
    }
}

/// The calls of one function, or the message of the first misuse Python reports.
pub(crate) fn function_calls(
    function: &StmtFunctionDef,
    nodes: &[CpythonNode<'_>],
    names: &CallNames<'_>,
) -> Result<FunctionCalls, String> {
    let display: &str = names.display;
    let bound: HashSet<String> = bound_names(function, nodes);
    if let Some(shadowed) = first_sorted(
        bound
            .iter()
            .filter(|name| names.imported.contains_key(*name)),
    ) {
        return Err(format!(
            "Macro module '{display}' shadows imported macro '{shadowed}'; imported macros must \
             be called directly without shadowing"
        ));
    }
    let direct_calls: HashSet<NodeId> = nodes
        .iter()
        .filter_map(direct_call_name)
        .map(std::ptr::from_ref)
        .collect();
    let mut dependencies: Vec<String> = Vec::new();
    let mut helpers: Vec<String> = Vec::new();
    for node in nodes {
        if let CpythonNode::Expr(expression @ Expr::Name(name)) = node {
            let direct: bool = direct_calls.contains(&std::ptr::from_ref(*expression));
            if !direct && names.imported.contains_key(name.id.as_str()) {
                return Err(format!(
                    "Macro module '{display}' uses imported macro '{}' dynamically; call imported \
                     macros directly",
                    name.id
                ));
            }
            if !direct && names.functions.contains(name.id.as_str()) {
                return Err(format!(
                    "Macro module '{display}' uses local helper '{}' dynamically; call local \
                     macros and helpers directly",
                    name.id
                ));
            }
        }
        let Some(Expr::Name(called)) = direct_call_name(node) else {
            continue;
        };
        let called: &str = called.id.as_str();
        if let Some(imported) = names.imported.get(called) {
            dependencies.push(imported.clone());
        } else if names.functions.contains(called) {
            if bound.contains(called) {
                return Err(format!(
                    "Macro module '{display}' shadows local helper '{called}'; static macro \
                     dependency analysis cannot resolve this call"
                ));
            }
            helpers.push(called.to_owned());
        }
    }
    Ok(FunctionCalls {
        dependencies: unique(dependencies),
        helpers: unique(helpers),
    })
}

/// The values without repeats, first occurrence first, as `dict.fromkeys` keeps them.
pub(crate) fn unique(values: Vec<String>) -> Vec<String> {
    let mut seen: HashSet<String> = HashSet::new();
    values
        .into_iter()
        .filter(|value| seen.insert(value.clone()))
        .collect()
}

/// Reject an imported macro or local function named outside an ordinary function body.
pub(crate) fn validate_use_locations(
    module: &ModModule,
    names: &CallNames<'_>,
    runtime: &HashSet<NodeId>,
) -> Result<(), String> {
    let display: &str = names.display;
    let outside: Vec<(&str, NodeId)> =
        walk_breadth_first(module.body.iter().map(CpythonNode::Stmt).collect())
            .into_iter()
            .filter_map(|node| match node {
                CpythonNode::Expr(expression @ Expr::Name(name)) => {
                    Some((name.id.as_str(), std::ptr::from_ref(expression)))
                }
                _ => None,
            })
            .filter(|(_, id)| !runtime.contains(id))
            .collect();
    if let Some((name, _)) = outside
        .iter()
        .find(|(name, _)| names.imported.contains_key(*name))
    {
        return Err(format!(
            "Macro module '{display}' uses imported macro '{name}' outside an ordinary function \
             body; call imported macros directly from module-level macro or helper functions"
        ));
    }
    if let Some((name, _)) = outside
        .iter()
        .find(|(name, _)| names.functions.contains(*name))
    {
        return Err(format!(
            "Macro module '{display}' uses local helper '{name}' outside an ordinary function \
             body; call local macros and helpers directly from module-level macro or helper \
             functions"
        ));
    }
    Ok(())
}
