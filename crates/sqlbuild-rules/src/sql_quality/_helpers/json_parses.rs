//! SQBRSQL045: the same JSON payload column parsed more than once in one SELECT scope.

use std::borrow::Cow;
use std::collections::HashMap;

use polyglot_sql::expressions::{Column, Identifier};
use polyglot_sql::scope::walk_in_scope;
use polyglot_sql::tokens::Token;
use polyglot_sql::{DialectType, Expression, ExpressionWalk};

use crate::sql_lint::models::LintDiagnostic;
use crate::sql_quality::constants::REPEATED_JSON_PARSE;
use crate::sql_quality::models::QualityRequest;
use crate::sql_quality::syntax::{is_trivia, lower};

/// Significant tokens searched backwards from the column for the function name.
const MAX_FUNCTION_NAME_DISTANCE: usize = 32;
const PARSE_ONCE_FIX_REFUSAL: &str =
    "Parsing the payload once requires naming a column in the CTE that reads it";

/// An identifier normalised the way the dialect resolves it.
type IdentifierKey = String;

/// One JSON parse call whose argument resolves to a plain column.
struct ParseCall<'a> {
    function: &'static str,
    column: &'a Column,
    column_start: usize,
}

pub(crate) fn diagnostics(request: &QualityRequest<'_>) -> Vec<LintDiagnostic> {
    let functions: &[&'static str] = parse_functions(request.dialect);
    if functions.is_empty() {
        return Vec::new();
    }
    let mut found: Vec<LintDiagnostic> = Vec::new();
    for statement in request.statements {
        for node in statement.dfs() {
            if matches!(node, Expression::Select(_)) {
                found.extend(scope_diagnostics(
                    request.tokens,
                    node,
                    functions,
                    request.dialect,
                ));
            }
        }
    }
    found
}

/// JSON parse functions that take one string argument, by dialect, in upper case.
fn parse_functions(dialect: DialectType) -> &'static [&'static str] {
    match dialect {
        DialectType::Snowflake | DialectType::Databricks => &["PARSE_JSON", "TRY_PARSE_JSON"],
        DialectType::BigQuery => &["PARSE_JSON", "SAFE.PARSE_JSON"],
        DialectType::DuckDB => &["JSON"],
        _ => &[],
    }
}

fn scope_diagnostics(
    tokens: &[Token],
    select: &Expression,
    functions: &[&'static str],
    dialect: DialectType,
) -> Vec<LintDiagnostic> {
    let quote: char = identifier_quote(dialect);
    let mut calls: Vec<ParseCall<'_>> = walk_in_scope(select, false)
        .filter_map(|node| parse_call(node, functions))
        .collect();
    calls.sort_by_key(|call| call.column_start);
    let mut groups: HashMap<
        (&'static str, Option<IdentifierKey>, IdentifierKey),
        Vec<&ParseCall<'_>>,
    > = HashMap::new();
    for call in &calls {
        let qualifier: Option<IdentifierKey> = call
            .column
            .table
            .as_ref()
            .map(|table| identifier_key(table, dialect));
        groups
            .entry((
                call.function,
                qualifier,
                identifier_key(&call.column.name, dialect),
            ))
            .or_default()
            .push(call);
    }
    let mut found: Vec<LintDiagnostic> = Vec::new();
    for group in groups.values().filter(|group| group.len() > 1) {
        let second: &ParseCall<'_> = group[1];
        let (start, end) = function_span(tokens, second);
        found.push(LintDiagnostic {
            code: REPEATED_JSON_PARSE.code,
            message: REPEATED_JSON_PARSE.message,
            remediation: Cow::Owned(remediation(second, group.len(), quote)),
            start,
            end,
            fix: None,
            fix_unavailable_reason: Some(PARSE_ONCE_FIX_REFUSAL),
        });
    }
    found
}

/// Normalises a name the way the dialect resolves it (Snowflake folds unquoted names upward).
fn identifier_key(identifier: &Identifier, dialect: DialectType) -> IdentifierKey {
    match dialect {
        DialectType::Snowflake if identifier.quoted => identifier.name.clone(),
        DialectType::Snowflake => identifier.name.to_uppercase(),
        _ => lower(&identifier.name),
    }
}

fn parse_call<'a>(node: &'a Expression, functions: &[&'static str]) -> Option<ParseCall<'a>> {
    let (name, argument): (&str, &Expression) = match node {
        Expression::ParseJson(function) => ("PARSE_JSON", &function.this),
        Expression::Function(function) if function.args.len() == 1 => {
            (function.name.as_str(), &function.args[0])
        }
        _ => return None,
    };
    let function: &'static str = functions
        .iter()
        .copied()
        .find(|candidate| candidate.eq_ignore_ascii_case(name))?;
    let column: &Column = unwrap_column(argument)?;
    let column_start: usize = column.span.or(column.name.span)?.start;
    Some(ParseCall {
        function,
        column,
        column_start,
    })
}

/// The column under wrappers that keep the parsed value tied to that column.
fn unwrap_column(expression: &Expression) -> Option<&Column> {
    let mut current: &Expression = expression;
    loop {
        current = match current {
            Expression::Column(column) => return Some(column),
            Expression::Paren(paren) => &paren.this,
            Expression::Lower(function) | Expression::Upper(function) => &function.this,
            Expression::Trim(trim) if trim.characters.is_none() => &trim.this,
            Expression::Cast(cast) | Expression::TryCast(cast) | Expression::SafeCast(cast) => {
                &cast.this
            }
            Expression::Coalesce(coalesce) if coalesce.expressions.len() == 1 => {
                &coalesce.expressions[0]
            }
            _ => return None,
        };
    }
}

/// Span of the function-name token that opens `call`, or of its column when not found.
fn function_span(tokens: &[Token], call: &ParseCall<'_>) -> (usize, usize) {
    let bare: &str = call.function.rsplit('.').next().unwrap_or(call.function);
    let before: usize = tokens.partition_point(|token| token.span.start < call.column_start);
    tokens[..before]
        .iter()
        .rev()
        .filter(|token| !is_trivia(token))
        .take(MAX_FUNCTION_NAME_DISTANCE)
        .find(|token| token.text.eq_ignore_ascii_case(bare))
        .map_or((call.column_start, call.column_start), |token| {
            (token.span.start, token.span.end)
        })
}

fn remediation(call: &ParseCall<'_>, count: usize, quote: char) -> String {
    let name: String = written(&call.column.name, quote);
    let column: String = call.column.table.as_ref().map_or_else(
        || name.clone(),
        |table| format!("{}.{name}", written(table, quote)),
    );
    let function: &str = call.function;
    format!(
        "{function}({column}) is parsed {count} times in one SELECT. Parse it once in the CTE that reads it, for example `{function}({name}) AS payload`, and read every field from that column in a later step."
    )
}

/// The identifier as authored, re-quoted with the dialect's identifier quote when it was quoted.
fn written(identifier: &Identifier, quote: char) -> String {
    if identifier.quoted {
        let escaped: String = identifier.name.replace(quote, &format!("{quote}{quote}"));
        format!("{quote}{escaped}{quote}")
    } else {
        identifier.name.clone()
    }
}

fn identifier_quote(dialect: DialectType) -> char {
    match dialect {
        DialectType::BigQuery | DialectType::Databricks => '`',
        _ => '"',
    }
}
