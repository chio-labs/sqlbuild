//! The context parameter, the SQL argument of a call and its literal text.

use ruff_python_ast::{Expr, ExprCall, Parameters};

use crate::cpython_tree::main::joined_values::joined_values;
use crate::cpython_tree::models::CpythonNode;
use crate::literal_sql::constants::{CONTEXT_PARAMETER_NAMES, SQL_PARAMETER_NAME};

/// The first well-known context parameter name, else the first parameter, ignoring `*args` and `**kwargs`.
pub(crate) fn context_name(parameters: &Parameters) -> Option<&str> {
    let names: Vec<&str> = parameters
        .posonlyargs
        .iter()
        .chain(parameters.args.iter())
        .chain(parameters.kwonlyargs.iter())
        .map(|parameter| parameter.parameter.name.as_str())
        .collect();
    names
        .iter()
        .find(|name| CONTEXT_PARAMETER_NAMES.contains(name))
        .or_else(|| names.first())
        .copied()
}

/// The first positional argument, else the `sql=` keyword, also inside a `**{...}` literal.
pub(crate) fn sql_argument(call: &ExprCall) -> Option<&Expr> {
    if let Some(first) = call.arguments.args.first() {
        return Some(first);
    }
    for keyword in &call.arguments.keywords {
        match &keyword.arg {
            Some(name) if name.as_str() == SQL_PARAMETER_NAME => return Some(&keyword.value),
            Some(_) => {}
            None => {
                let Expr::Dict(dict) = &keyword.value else {
                    continue;
                };
                for item in &dict.items {
                    if let Some(Expr::StringLiteral(key)) = &item.key
                        && key.value.to_str() == SQL_PARAMETER_NAME
                    {
                        return Some(&item.value);
                    }
                }
            }
        }
    }
    None
}

/// A string literal's text, or an f-string's with numbered placeholders for its values.
pub(crate) fn literal_text(expression: &Expr, placeholder: &str) -> Option<String> {
    match expression {
        Expr::StringLiteral(literal) => Some(literal.value.to_str().to_owned()),
        Expr::FString(_) => Some(
            joined_values(expression)
                .iter()
                .enumerate()
                .map(|(index, value)| match value {
                    CpythonNode::Text(constant) => constant.value.clone(),
                    _ => format!("{placeholder}{index}"),
                })
                .collect(),
        ),
        _ => None,
    }
}
