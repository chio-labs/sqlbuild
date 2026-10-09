//! Python's `_function_errors`: argument counts and families of declared function calls.

use std::collections::HashMap;

use polyglot_sql::expressions::{Column, Function, Literal, Select};
use polyglot_sql::{Expression, ExpressionWalk};

use crate::semantic_checks::_helpers::metadata_checks::argument_types::expression_type;
use crate::semantic_checks::_helpers::metadata_checks::families::Families;
use crate::semantic_checks::_helpers::sql_text::parsed_sql::parsed_model;
use crate::semantic_checks::_helpers::sql_text::text::{ascii, casefold};
use crate::semantic_checks::constants::{
    ARGUMENT_COUNT_CODE, NUMBER_LITERAL_TYPE, STRING_LITERAL_TYPE, TYPE_MISMATCH_CODE,
    UDF_NAME_PREFIX, UNKNOWN_TYPE,
};
use crate::semantic_checks::models::{MetadataFunction, MetadataModel, SemanticDeferral};

/// One function error before it is located: `(code, located name, message)`.
pub(crate) type FunctionError = (&'static str, String, String);

/// Everything `_function_errors` reads beside the model.
pub(crate) struct FunctionContext<'a> {
    pub(crate) dialect: Option<&'a str>,
    pub(crate) functions: &'a HashMap<&'a str, &'a MetadataFunction>,
    pub(crate) shapes: &'a HashMap<&'a str, &'a [(String, String)]>,
    pub(crate) return_types: &'a HashMap<String, String>,
    pub(crate) families: &'a Families,
}

/// One declared function call, the index of its nearest select, and its declaration.
struct DeclaredCall<'a> {
    call: &'a Function,
    select: Option<usize>,
    function: &'a MetadataFunction,
}

/// Case-folded column types of one relation shape, preserving declaration order per name.
type FoldedShape = HashMap<String, Vec<String>>;

/// The B102 and B301 errors of one model's declared function calls.
pub(crate) fn function_errors(
    model: &MetadataModel,
    context: &FunctionContext<'_>,
) -> Result<Vec<FunctionError>, SemanticDeferral> {
    if context.functions.is_empty() || !model.calls_functions {
        return Ok(Vec::new());
    }
    let Some(parsed) = parsed_model(&model.query_sql, context.dialect)? else {
        return Ok(Vec::new());
    };
    let (calls, selects) = declared_calls(&parsed, context.functions)?;
    let mut relations: HashMap<usize, Vec<&Expression>> = HashMap::new();
    for call in &calls {
        if let Some(select) = call.select
            && resolves_argument_columns(call)
        {
            relations
                .entry(select)
                .or_insert_with(|| select_relations(selects[select]));
        }
    }
    let folded: HashMap<&str, FoldedShape> = folded_shapes(&relations, context.shapes)?;
    let mut errors: Vec<FunctionError> = Vec::new();
    for call in &calls {
        let name: String = call_name(call.call).to_owned();
        let declared: &[(String, String)] = &call.function.arguments;
        if call.call.args.len() != declared.len() {
            let message = format!(
                "Function '{name}' expects {} arguments but received {}",
                declared.len(),
                call.call.args.len()
            );
            errors.push((ARGUMENT_COUNT_CODE, name, message));
            continue;
        }
        let scope: Option<&[&Expression]> = call
            .select
            .and_then(|select| relations.get(&select))
            .map(Vec::as_slice);
        for (argument, (argument_name, argument_type)) in call.call.args.iter().zip(declared) {
            let actual: String = argument_type_of(argument, scope, &folded, context)?;
            if actual != UNKNOWN_TYPE && context.families.different(&actual, argument_type)? {
                let message = format!(
                    "Function '{name}' argument '{argument_name}' expects {argument_type}, \
                     received {actual}; convert the argument explicitly"
                );
                errors.push((TYPE_MISMATCH_CODE, name.clone(), message));
            }
        }
    }
    Ok(errors)
}

fn call_name(call: &Function) -> &str {
    call.name
        .strip_prefix(UDF_NAME_PREFIX)
        .unwrap_or(&call.name)
}

/// Python's `_declared_function_calls` over `_function_scopes`' pre-order walk.
fn declared_calls<'a>(
    root: &'a Expression,
    functions: &HashMap<&str, &'a MetadataFunction>,
) -> Result<(Vec<DeclaredCall<'a>>, Vec<&'a Select>), SemanticDeferral> {
    let mut calls: Vec<DeclaredCall<'a>> = Vec::new();
    let mut selects: Vec<&'a Select> = Vec::new();
    let mut pending: Vec<(&'a Expression, Option<usize>)> = vec![(root, None)];
    while let Some((node, mut scope)) = pending.pop() {
        match node {
            Expression::Select(select) => {
                scope = Some(selects.len());
                selects.push(select);
            }
            Expression::Function(call) => {
                let key: String = casefold(ascii(call_name(call))?);
                if let Some(function) = functions.get(key.as_str()) {
                    calls.push(DeclaredCall {
                        call,
                        select: scope,
                        function,
                    });
                }
            }
            _ => {}
        }
        for child in node.children().into_iter().rev() {
            pending.push((child, scope));
        }
    }
    Ok((calls, selects))
}

/// Python's `_resolves_argument_columns`.
fn resolves_argument_columns(call: &DeclaredCall<'_>) -> bool {
    call.call.args.len() == call.function.arguments.len()
        && call
            .call
            .args
            .iter()
            .any(|argument| matches!(argument, Expression::Column(_)))
}

/// Python's `_select_relations`: FROM expressions, then each join's relation.
fn select_relations(select: &Select) -> Vec<&Expression> {
    let mut relations: Vec<&Expression> = select
        .from
        .as_ref()
        .map(|from| from.expressions.iter().collect())
        .unwrap_or_default();
    relations.extend(select.joins.iter().map(|join| &join.this));
    relations
}

/// Python's `_relation_table_name` and the alias `_argument_column_type` compares.
fn relation_names(relation: &Expression) -> (&str, &str) {
    match relation {
        Expression::Table(table) => (
            table.name.name.as_str(),
            table
                .alias
                .as_ref()
                .map_or(table.name.name.as_str(), |alias| alias.name.as_str()),
        ),
        _ => ("", ""),
    }
}

/// Python's `folded_shapes` for the tables the resolving selects read.
fn folded_shapes<'a>(
    relations: &HashMap<usize, Vec<&'a Expression>>,
    shapes: &HashMap<&str, &[(String, String)]>,
) -> Result<HashMap<&'a str, FoldedShape>, SemanticDeferral> {
    let mut folded: HashMap<&'a str, FoldedShape> = HashMap::new();
    for relation in relations.values().flatten() {
        let (table_name, _) = relation_names(relation);
        let Some(shape) = shapes.get(table_name) else {
            continue;
        };
        if folded.contains_key(table_name) {
            continue;
        }
        let mut columns: FoldedShape = HashMap::new();
        for (name, column_type) in *shape {
            columns
                .entry(casefold(ascii(name)?))
                .or_default()
                .push(column_type.clone());
        }
        folded.insert(table_name, columns);
    }
    Ok(folded)
}

/// The type `_function_errors` compares for one argument.
fn argument_type_of(
    argument: &Expression,
    scope: Option<&[&Expression]>,
    folded: &HashMap<&str, FoldedShape>,
    context: &FunctionContext<'_>,
) -> Result<String, SemanticDeferral> {
    match argument {
        Expression::Literal(literal) => Ok(match literal.as_ref() {
            Literal::String(_) => STRING_LITERAL_TYPE,
            Literal::Number(_) => NUMBER_LITERAL_TYPE,
            _ => UNKNOWN_TYPE,
        }
        .to_owned()),
        Expression::Column(column) => argument_column_type(column, scope, folded),
        _ => Ok(expression_type(argument, context.return_types)?
            .unwrap_or_else(|| UNKNOWN_TYPE.to_owned())),
    }
}

/// Python's `_argument_column_type`: the only matching column type among the select's inputs.
fn argument_column_type(
    column: &Column,
    scope: Option<&[&Expression]>,
    folded: &HashMap<&str, FoldedShape>,
) -> Result<String, SemanticDeferral> {
    let Some(relations) = scope else {
        return Ok(UNKNOWN_TYPE.to_owned());
    };
    let qualifier: Option<String> = match &column.table {
        Some(table) => Some(casefold(ascii(&table.name)?)),
        None => None,
    };
    let name: String = casefold(ascii(&column.name.name)?);
    let mut candidates: Vec<&String> = Vec::new();
    for relation in relations {
        let (table_name, alias) = relation_names(relation);
        if let Some(qualifier) = &qualifier
            && *qualifier != casefold(ascii(alias)?)
        {
            continue;
        }
        let Some(shape) = folded.get(table_name) else {
            return Ok(UNKNOWN_TYPE.to_owned());
        };
        candidates.extend(shape.get(&name).into_iter().flatten());
    }
    Ok(match candidates.as_slice() {
        [only] => (*only).clone(),
        _ => UNKNOWN_TYPE.to_owned(),
    })
}
