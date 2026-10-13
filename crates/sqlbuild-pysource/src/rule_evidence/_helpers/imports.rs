//! Import bindings, module assignments and the pytest and harness names a test module uses.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExprCall, Number, Stmt};
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::rule_evidence::constants::{
    FLOAT_ZERO, PARAMETRIZE_ATTRIBUTE, PYTEST_MARK_ATTRIBUTE, PYTEST_MODULE_NAME,
};
use crate::rule_evidence::types::Imports;

/// Each top-level import's bound name; relative `from` imports bind nothing here.
pub(crate) fn imports(body: &[Stmt]) -> Imports {
    let mut result: Imports = HashMap::new();
    for statement in body {
        match statement {
            Stmt::Import(import) => {
                for alias in &import.names {
                    let name: &str = alias.name.as_str();
                    let bound: &str = alias.asname.as_ref().map_or_else(
                        || name.split('.').next().unwrap_or(name),
                        |asname| asname.as_str(),
                    );
                    result.insert(bound.to_owned(), (name.to_owned(), None));
                }
            }
            Stmt::ImportFrom(import) if import.level == 0 => {
                let Some(module) = &import.module else {
                    continue;
                };
                for alias in &import.names {
                    let bound: &str = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
                    result.insert(
                        bound.to_owned(),
                        (
                            module.as_str().to_owned(),
                            Some(alias.name.as_str().to_owned()),
                        ),
                    );
                }
            }
            _ => {}
        }
    }
    result
}

/// Each module-level name's last assigned value.
pub(crate) fn assignments(body: &[Stmt]) -> HashMap<&str, &Expr> {
    let mut result: HashMap<&str, &Expr> = HashMap::new();
    for statement in body {
        let (targets, value): (Vec<&Expr>, Option<&Expr>) = match statement {
            Stmt::Assign(assign) => (assign.targets.iter().collect(), Some(&assign.value)),
            Stmt::AnnAssign(assign) => (vec![&*assign.target], assign.value.as_deref()),
            _ => continue,
        };
        let Some(value) = value else {
            continue;
        };
        for target in targets {
            if let Expr::Name(name) = target {
                result.insert(name.id.as_str(), value);
            }
        }
    }
    result
}

/// The module's classes and every name imported from a module.
pub(crate) fn constructors(body: &[Stmt], imports: &Imports) -> HashSet<String> {
    let mut declared: HashSet<String> = body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(class) => Some(class.name.as_str().to_owned()),
            _ => None,
        })
        .collect();
    declared.extend(
        imports
            .iter()
            .filter(|(_, (_, symbol))| symbol.is_some())
            .map(|(name, _)| name.clone()),
    );
    declared
}

/// Whether `expression` names `symbol` imported from one of `modules`.
pub(crate) fn is_imported_symbol(
    expression: &Expr,
    imports: &Imports,
    modules: &[String],
    symbol: &str,
) -> bool {
    match expression {
        Expr::Name(name) => imports
            .get(name.id.as_str())
            .is_some_and(|(module, imported)| {
                modules.contains(module) && imported.as_deref() == Some(symbol)
            }),
        Expr::Attribute(attribute) => {
            let Expr::Name(base) = &*attribute.value else {
                return false;
            };
            let Some((module, imported)) = imports.get(base.id.as_str()) else {
                return false;
            };
            if attribute.attr.as_str() != symbol {
                return false;
            }
            let qualified: String = match imported {
                None => module.clone(),
                Some(imported) => format!("{module}.{imported}"),
            };
            modules.contains(&qualified)
        }
        _ => false,
    }
}

/// The value of the first `name=` keyword of `call`.
pub(crate) fn keyword<'a>(call: &'a ExprCall, name: &str) -> Option<&'a Expr> {
    call.arguments
        .keywords
        .iter()
        .find(|keyword| keyword.arg.as_ref().is_some_and(|arg| arg.as_str() == name))
        .map(|keyword| &keyword.value)
}

/// Whether `expression` is `pytest.mark.<attribute>` through a plain `import pytest`.
pub(crate) fn is_pytest_mark(expression: &Expr, imports: &Imports, mark: &str) -> bool {
    let Expr::Attribute(attribute) = expression else {
        return false;
    };
    let Expr::Attribute(marks) = &*attribute.value else {
        return false;
    };
    let Expr::Name(module) = &*marks.value else {
        return false;
    };
    attribute.attr.as_str() == mark
        && marks.attr.as_str() == PYTEST_MARK_ATTRIBUTE
        && imports.get(module.id.as_str()) == Some(&(PYTEST_MODULE_NAME.to_owned(), None))
}

pub(crate) fn is_parametrize_call(expression: &Expr, imports: &Imports) -> bool {
    is_pytest_mark(expression, imports, PARAMETRIZE_ATTRIBUTE)
}

/// The parameter names a `parametrize` argument-names expression declares.
pub(crate) fn parameter_names(expression: &Expr) -> Vec<String> {
    match expression {
        Expr::StringLiteral(text) => text
            .value
            .to_str()
            .split(',')
            .map(|name| python_strip(name).to_owned())
            .collect(),
        Expr::List(list) => string_items(&list.elts),
        Expr::Tuple(tuple) => string_items(&tuple.elts),
        _ => Vec::new(),
    }
}

fn string_items(items: &[Expr]) -> Vec<String> {
    let mut values: Vec<String> = Vec::with_capacity(items.len());
    for item in items {
        let Expr::StringLiteral(text) = item else {
            return Vec::new();
        };
        values.push(text.value.to_str().to_owned());
    }
    values
}

/// `bool(node.value)` for an `ast.Constant`, or `None` for any other expression.
pub(crate) fn constant_truth(expression: &Expr) -> Option<bool> {
    Some(match expression {
        Expr::BooleanLiteral(literal) => literal.value,
        Expr::NoneLiteral(_) => false,
        Expr::EllipsisLiteral(_) => true,
        Expr::StringLiteral(text) => !text.value.is_empty(),
        Expr::BytesLiteral(bytes) => bytes.value.bytes().next().is_some(),
        Expr::NumberLiteral(number) => match &number.value {
            Number::Int(value) => *value != ruff_python_ast::Int::ZERO,
            Number::Float(value) => *value != FLOAT_ZERO,
            Number::Complex { real, imag } => *real != FLOAT_ZERO || *imag != FLOAT_ZERO,
        },
        _ => return None,
    })
}

/// Whether `expression` is the `True` constant.
pub(crate) fn is_true_constant(expression: &Expr) -> bool {
    matches!(expression, Expr::BooleanLiteral(literal) if literal.value)
}

/// The UTF-8 text of the file at `path`; an unreadable file reads as empty, as Python skips it.
pub(crate) fn read_source(path: &std::path::Path) -> String {
    let Ok(bytes) = std::fs::read(path) else {
        return String::new();
    };
    let Ok(text) = String::from_utf8(bytes) else {
        return String::new();
    };
    text
}
