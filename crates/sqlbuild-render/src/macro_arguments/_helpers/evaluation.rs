//! Evaluate parsed nodes in Python's order into argument values, and walk typed references.

use std::collections::VecDeque;

use crate::macro_arguments::_helpers::failures::{
    Failure, bytes_literal, complex_literal, dict_unpacking, ellipsis, formatted_string,
    keyword_expansion, typed_reference, unary, unsupported,
};
use crate::macro_arguments::_helpers::lexer::NumberToken;
use crate::macro_arguments::_helpers::syntax_tree::{CallArguments, Expr, Keyword, Node};
use crate::macro_arguments::models::{ArgumentValue, MacroArguments};

const TYPED_REFERENCE_FUNCTIONS: [&str; 3] = ["__ref", "__source", "__seed"];

/// Positional values, then keyword values, failing at the first node Python would reject.
pub(crate) fn evaluate_arguments(arguments: &CallArguments) -> Result<MacroArguments, Failure> {
    let positional: Vec<ArgumentValue> = arguments
        .args
        .iter()
        .map(evaluate)
        .collect::<Result<_, _>>()?;
    let mut keywords: Vec<(String, ArgumentValue)> = Vec::with_capacity(arguments.keywords.len());
    for keyword in &arguments.keywords {
        let Some(name) = &keyword.name else {
            return Err(keyword_expansion(keyword.value.position));
        };
        keywords.push((name.clone(), evaluate(&keyword.value)?));
    }
    Ok(MacroArguments {
        positional,
        keywords,
        typed_references: walked_references(arguments),
    })
}

fn evaluate(node: &Node) -> Result<ArgumentValue, Failure> {
    let position: usize = node.position;
    match &node.expr {
        Expr::Str { bytes: true, .. } => Err(bytes_literal(position)),
        Expr::Str {
            formatted: true, ..
        } => Err(formatted_string(position)),
        Expr::Str { value, .. } => Ok(ArgumentValue::Str(value.clone())),
        Expr::Number(NumberToken::Int { radix, digits }) => Ok(ArgumentValue::Int {
            radix: *radix,
            digits: digits.clone(),
        }),
        Expr::Number(NumberToken::Float(text)) => Ok(ArgumentValue::Float(text.clone())),
        Expr::Number(NumberToken::Complex) => Err(complex_literal(position)),
        Expr::Ellipsis => Err(ellipsis(position)),
        Expr::Name(name) => match name.as_str() {
            "True" => Ok(ArgumentValue::Bool(true)),
            "False" => Ok(ArgumentValue::Bool(false)),
            "None" => Ok(ArgumentValue::None),
            _ => Err(unsupported(position)),
        },
        Expr::Nested(call) => Ok(ArgumentValue::NestedCall(*call)),
        Expr::Call {
            function,
            args,
            keywords,
        } => typed_reference_value(function, args, keywords, position),
        Expr::List(items) => Ok(ArgumentValue::List(evaluate_all(items)?)),
        Expr::Tuple(items) => Ok(ArgumentValue::Tuple(evaluate_all(items)?)),
        Expr::Dict(pairs) => {
            let mut values: Vec<(ArgumentValue, ArgumentValue)> = Vec::with_capacity(pairs.len());
            for (key, value) in pairs {
                let Some(key) = key else {
                    return Err(dict_unpacking(value.position));
                };
                values.push((evaluate(key)?, evaluate(value)?));
            }
            Ok(ArgumentValue::Dict(values))
        }
        Expr::Set(_) | Expr::Starred(_) => Err(unsupported(position)),
        Expr::Unary { negative, operand } => {
            let value: ArgumentValue = evaluate(operand)?;
            if !is_number(&value) {
                return Err(unary(position));
            }
            Ok(if *negative {
                ArgumentValue::Negative(Box::new(value))
            } else {
                ArgumentValue::Positive(Box::new(value))
            })
        }
    }
}

fn evaluate_all(items: &[Node]) -> Result<Vec<ArgumentValue>, Failure> {
    items.iter().map(evaluate).collect()
}

/// Python's `isinstance(value, int | float)`, deferring a nested call's value to Python.
fn is_number(value: &ArgumentValue) -> bool {
    match value {
        ArgumentValue::Int { .. }
        | ArgumentValue::Float(_)
        | ArgumentValue::Bool(_)
        | ArgumentValue::NestedCall(_) => true,
        ArgumentValue::Negative(inner) | ArgumentValue::Positive(inner) => is_number(inner),
        _ => false,
    }
}

fn typed_reference_value(
    function: &Node,
    args: &[Node],
    keywords: &[Keyword],
    position: usize,
) -> Result<ArgumentValue, Failure> {
    let Expr::Name(name) = &function.expr else {
        return Err(unsupported(position));
    };
    if !TYPED_REFERENCE_FUNCTIONS.contains(&name.as_str()) {
        return Err(unsupported(position));
    }
    match (args, keywords) {
        (
            [
                Node {
                    expr:
                        Expr::Str {
                            value,
                            bytes: false,
                            formatted: false,
                        },
                    ..
                },
            ],
            [],
        ) if !value.is_empty() => Ok(ArgumentValue::TypedReference {
            function: name.clone(),
            name: value.clone(),
        }),
        _ => Err(typed_reference(name, position)),
    }
}

enum Walked<'tree> {
    Node(&'tree Node),
    Keyword(&'tree Keyword),
}

/// Every typed reference call in `ast.walk` order: breadth first, fields in `_fields` order.
fn walked_references(arguments: &CallArguments) -> Vec<(String, String)> {
    let mut pending: VecDeque<Walked<'_>> = arguments
        .args
        .iter()
        .map(Walked::Node)
        .chain(arguments.keywords.iter().map(Walked::Keyword))
        .collect();
    let mut references: Vec<(String, String)> = Vec::new();
    while let Some(walked) = pending.pop_front() {
        let node: &Node = match walked {
            Walked::Keyword(keyword) => {
                pending.push_back(Walked::Node(&keyword.value));
                continue;
            }
            Walked::Node(node) => node,
        };
        match &node.expr {
            Expr::Call {
                function,
                args,
                keywords,
            } => {
                if let (
                    Expr::Name(name),
                    [
                        Node {
                            expr: Expr::Str { value, .. },
                            ..
                        },
                    ],
                ) = (&function.expr, args.as_slice())
                {
                    references.push((name.clone(), value.clone()));
                }
                pending.push_back(Walked::Node(function));
                pending.extend(args.iter().map(Walked::Node));
                pending.extend(keywords.iter().map(Walked::Keyword));
            }
            Expr::List(items) | Expr::Tuple(items) | Expr::Set(items) => {
                pending.extend(items.iter().map(Walked::Node));
            }
            Expr::Dict(pairs) => {
                pending.extend(
                    pairs
                        .iter()
                        .filter_map(|(key, _)| key.as_ref().map(Walked::Node)),
                );
                pending.extend(pairs.iter().map(|(_, value)| Walked::Node(value)));
            }
            Expr::Starred(inner) | Expr::Unary { operand: inner, .. } => {
                pending.push_back(Walked::Node(inner));
            }
            _ => {}
        }
    }
    references
}
