//! The `RuleCase(...)` calls a harness call's `test_case` argument statically resolves to.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExprCall, Stmt};

use crate::rule_evidence::_helpers::imports::{
    is_imported_symbol, is_parametrize_call, parameter_names,
};
use crate::rule_evidence::constants::{
    MIN_PARAMETRIZE_ARGUMENTS, PUBLIC_HARNESS_MODULES, RULE_CASE,
};
use crate::rule_evidence::types::Imports;

/// The module bindings case resolution reads.
pub(crate) struct CaseScope<'a, 'b> {
    pub(crate) imports: &'b Imports,
    pub(crate) assignments: &'b HashMap<&'a str, &'a Expr>,
    pub(crate) constructors: &'b HashSet<String>,
}

fn harness_modules() -> Vec<String> {
    PUBLIC_HARNESS_MODULES
        .iter()
        .map(|module| (*module).to_owned())
        .collect()
}

fn declared_cases<'a>(
    expression: &'a Expr,
    field: Option<&str>,
    scope: &CaseScope<'a, '_>,
    seen: &HashSet<&'a str>,
) -> Vec<&'a ExprCall> {
    if let Expr::Name(name) = expression
        && let Some(value) = scope.assignments.get(name.id.as_str())
        && !seen.contains(name.id.as_str())
    {
        let mut seen: HashSet<&'a str> = seen.clone();
        seen.insert(name.id.as_str());
        return declared_cases(value, field, scope, &seen);
    }
    let items: Option<&'a [Expr]> = match expression {
        Expr::List(list) => Some(&list.elts),
        Expr::Tuple(tuple) => Some(&tuple.elts),
        Expr::Set(set) => Some(&set.elts),
        _ => None,
    };
    if let Some(items) = items {
        return items
            .iter()
            .flat_map(|item| declared_cases(item, field, scope, seen))
            .collect();
    }
    let Expr::Call(call) = expression else {
        return Vec::new();
    };
    let Some(field) = field else {
        if is_imported_symbol(&call.func, scope.imports, &harness_modules(), RULE_CASE) {
            return vec![call];
        }
        return Vec::new();
    };
    let Expr::Name(constructor) = &*call.func else {
        return Vec::new();
    };
    if !scope.constructors.contains(constructor.id.as_str()) {
        return Vec::new();
    }
    call.arguments
        .keywords
        .iter()
        .find(|keyword| {
            keyword
                .arg
                .as_ref()
                .is_some_and(|arg| arg.as_str() == field)
        })
        .map(|keyword| declared_cases(&keyword.value, None, scope, seen))
        .unwrap_or_default()
}

/// The values `pytest.mark.parametrize` binds to `parameter` on `owner`.
fn parametrized_values<'a>(
    decorators: &'a [ruff_python_ast::Decorator],
    parameter: &str,
    imports: &Imports,
) -> Option<&'a Expr> {
    decorators.iter().find_map(|decorator| {
        let Expr::Call(call) = &decorator.expression else {
            return None;
        };
        let args: &[Expr] = &call.arguments.args;
        (is_parametrize_call(&call.func, imports)
            && args.len() >= MIN_PARAMETRIZE_ARGUMENTS
            && parameter_names(&args[0]) == [parameter])
        .then(|| &args[1])
    })
}

/// The case declarations a `test_case` argument names, directly or through `parametrize`.
pub(crate) fn case_declarations<'a>(
    expression: &'a Expr,
    owner: &'a Stmt,
    scope: &CaseScope<'a, '_>,
) -> Vec<&'a ExprCall> {
    let direct: Vec<&'a ExprCall> = declared_cases(expression, None, scope, &HashSet::new());
    if !direct.is_empty() {
        return direct;
    }
    let (parameter, field): (&str, Option<&str>) = match expression {
        Expr::Name(name) => (name.id.as_str(), None),
        Expr::Attribute(attribute) => match &*attribute.value {
            Expr::Name(name) => (name.id.as_str(), Some(attribute.attr.as_str())),
            _ => return Vec::new(),
        },
        _ => return Vec::new(),
    };
    let Stmt::FunctionDef(function) = owner else {
        return Vec::new();
    };
    parametrized_values(&function.decorator_list, parameter, scope.imports)
        .map(|values| declared_cases(values, field, scope, &HashSet::new()))
        .unwrap_or_default()
}
