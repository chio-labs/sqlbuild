//! A SQL macro body parsed as SQL, its parameter references located and replaced in place.

use polyglot_sql::expressions::{Identifier, Select};
use polyglot_sql::{DialectType, Expression, ExpressionWalk};

use crate::sql_macros::_helpers::arguments::is_atomic;
use crate::sql_macros::_helpers::lexing::{Token, tokens};
use crate::sql_macros::_helpers::parameters::{
    ParameterReference, alias_follows, parameter_references, placeholder, placeholder_parameter,
    with_placeholders,
};
use crate::sql_macros::constants::{ARGUMENT_CODE, INVALID_DEFINITION_CODE};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{
    ArgumentShape, BodyExpansion, ParameterKind, RenderedArgument, SqlMacroDefinition,
    SqlMacroForm, SqlMacroParameter,
};

/// Dialects tried in turn to parse a body; the first that parses it locates its references.
const PARSE_DIALECTS: [DialectType; 8] = [
    DialectType::Generic,
    DialectType::DuckDB,
    DialectType::Snowflake,
    DialectType::BigQuery,
    DialectType::PostgreSQL,
    DialectType::Databricks,
    DialectType::ClickHouse,
    DialectType::TSQL,
];
const EXPRESSION_PREFIX: &str = "SELECT ";
const CTE_SUFFIX: &str = "\nSELECT 1";

/// The body parsed as SQL.
struct ParsedBody {
    select: Box<Select>,
}

fn parsed(form: SqlMacroForm, body: &str) -> Result<ParsedBody, String> {
    let text: String = match form {
        SqlMacroForm::Expression => format!("{EXPRESSION_PREFIX}{body}"),
        SqlMacroForm::CteList => format!("{body}{CTE_SUFFIX}"),
        SqlMacroForm::ColumnList => body.to_owned(),
    };
    let mut first_error: Option<String> = None;
    for dialect in PARSE_DIALECTS {
        match polyglot_sql::parse(&text, dialect) {
            Ok(mut statements) if statements.len() == 1 => {
                if let Some(Expression::Select(select)) = statements.pop() {
                    return Ok(ParsedBody { select });
                }
                first_error.get_or_insert_with(|| "it is not a SELECT fragment".to_owned());
            }
            Ok(_) => {
                first_error.get_or_insert_with(|| "it holds more than one statement".to_owned());
            }
            Err(error) => {
                first_error.get_or_insert_with(|| error.to_string());
            }
        }
    }
    Err(first_error.unwrap_or_default())
}

/// The reason the parsed select is not exactly the form's fragment, if it is not.
fn shape_problem(form: SqlMacroForm, select: &Select) -> Option<&'static str> {
    let clauses: bool = select.from.is_some()
        || !select.joins.is_empty()
        || select.where_clause.is_some()
        || select.group_by.is_some()
        || select.having.is_some()
        || select.qualify.is_some()
        || select.order_by.is_some()
        || select.limit.is_some()
        || select.offset.is_some()
        || select.distinct;
    match form {
        SqlMacroForm::Expression => {
            if clauses || select.with.is_some() || select.expressions.len() != 1 {
                return Some("an expression macro body must be exactly one SQL expression");
            }
            if matches!(select.expressions[0], Expression::Alias(_)) {
                return Some(
                    "an expression macro body is an expression, not a named column; drop the alias",
                );
            }
            None
        }
        SqlMacroForm::CteList => {
            let with_list: bool = select.with.as_ref().is_some_and(|with| !with.recursive);
            if !with_list || clauses || select.expressions.len() != 1 {
                return Some(
                    "a CTE-list macro body must be only a WITH list of CTEs, with no final query",
                );
            }
            None
        }
        SqlMacroForm::ColumnList => {
            if clauses || select.with.is_some() || select.expressions.is_empty() {
                return Some(
                    "a column-list macro body must be only SELECT and its columns, with no FROM or other clauses",
                );
            }
            None
        }
    }
}

/// The parameter a parsed identifier stands for, when it is a placeholder of `@name`.
fn parameter_of<'a>(
    definition: &'a SqlMacroDefinition,
    identifier: &Identifier,
) -> Option<&'a SqlMacroParameter> {
    placeholder_parameter(&identifier.name).and_then(|name| definition.parameter(name))
}

/// The names a body defines: CTE names, or the output column names of a column list.
fn defined_names(
    definition: &SqlMacroDefinition,
    select: &Select,
    arguments: &[RenderedArgument],
) -> Result<Vec<String>, String> {
    match definition.form {
        SqlMacroForm::Expression => Ok(Vec::new()),
        SqlMacroForm::CteList => Ok(select
            .with
            .iter()
            .flat_map(|with| with.ctes.iter())
            .map(|cte| cte.alias.name.clone())
            .collect()),
        SqlMacroForm::ColumnList => {
            let mut names: Vec<String> = Vec::new();
            for projection in &select.expressions {
                let name: String = match projection {
                    Expression::Alias(alias) => alias.alias.name.clone(),
                    Expression::Column(column) => {
                        column_output_name(definition, column, arguments)?
                    }
                    _ => {
                        return Err(format!(
                            "every column of a column-list macro needs a name; add AS <name> to {}",
                            shown_projection(projection)
                        ));
                    }
                };
                names.push(name);
            }
            Ok(names)
        }
    }
}

/// The output name of a bare column projection: a `COLUMN OF` argument's column, or the name.
fn column_output_name(
    definition: &SqlMacroDefinition,
    column: &polyglot_sql::expressions::Column,
    arguments: &[RenderedArgument],
) -> Result<String, String> {
    let Some(parameter) = parameter_of(definition, &column.name) else {
        return Ok(column.name.name.clone());
    };
    if !matches!(parameter.kind, ParameterKind::ColumnOf { .. }) {
        return Err(format!(
            "every column of a column-list macro needs a name; add AS <name> to @{}",
            parameter.name
        ));
    }
    Ok(arguments
        .iter()
        .find(|argument| definition.parameters[argument.parameter].name == parameter.name)
        .map_or_else(|| parameter.name.clone(), |argument| argument.sql.clone()))
}

fn shown_projection(projection: &Expression) -> String {
    let text: String = polyglot_sql::generate(projection, DialectType::Generic)
        .unwrap_or_else(|_| projection.variant_name().to_owned());
    text.replace(&placeholder(""), "@")
}

/// Rejects a RELATION parameter read as a plain value, as in `SELECT @src`.
fn check_relation_values(definition: &SqlMacroDefinition, select: &Select) -> Result<(), String> {
    let root: Expression = Expression::Select(Box::new(select.clone()));
    for node in root.dfs() {
        if let Expression::Column(column) = node
            && column.table.is_none()
            && let Some(parameter) = parameter_of(definition, &column.name)
            && matches!(parameter.kind, ParameterKind::Relation { .. })
        {
            let name: &str = &parameter.name;
            return Err(format!(
                "RELATION argument {name} is used as a value; read its columns instead, such as @{name}.column"
            ));
        }
    }
    Ok(())
}

/// The text replacing one `@name` reference, from its argument and where it stands.
fn substituted(
    kind: &ParameterKind,
    parameter: &str,
    argument: &RenderedArgument,
    (sql, scanned, token): (&str, &[Token], usize),
) -> String {
    match kind {
        ParameterKind::Relation { .. } => {
            let qualifier: bool = scanned
                .get(token + 1)
                .is_some_and(|dot| dot.is(sql, ".") && dot.start == scanned[token].end);
            match &argument.shape {
                ArgumentShape::Reference { .. } if qualifier => parameter.to_owned(),
                ArgumentShape::Reference { call } if alias_follows(sql, scanned, token) => {
                    call.clone()
                }
                ArgumentShape::Reference { call } => format!("{call} AS {parameter}"),
                _ => argument.sql.clone(),
            }
        }
        ParameterKind::Expression { .. } | ParameterKind::Any | ParameterKind::Constant { .. }
            if !is_atomic(&argument.sql) =>
        {
            format!("({})", argument.sql)
        }
        _ => argument.sql.clone(),
    }
}

/// `body` with each `@name` replaced by its argument, token by token.
fn substituted_body(
    definition: &SqlMacroDefinition,
    (body, scanned, references): (&str, &[Token], &[ParameterReference]),
    arguments: &[RenderedArgument],
) -> String {
    let mut expanded: String = String::with_capacity(body.len());
    let mut cursor: usize = 0;
    for reference in references {
        let Some(argument) = arguments.iter().find(|argument| {
            definition.parameters[argument.parameter]
                .name
                .eq_ignore_ascii_case(&reference.name)
        }) else {
            continue;
        };
        let parameter = &definition.parameters[argument.parameter];
        expanded.push_str(&body[cursor..reference.start]);
        expanded.push_str(&substituted(
            &parameter.kind,
            &parameter.name,
            argument,
            (body, scanned, reference.token),
        ));
        cursor = reference.end;
    }
    expanded.push_str(&body[cursor..]);
    expanded
}

/// `body` with each parameter replaced by its argument, as the form inserts it at a call.
pub(crate) fn expand_body(
    definition: &SqlMacroDefinition,
    body: &str,
    arguments: &[RenderedArgument],
) -> Result<BodyExpansion, SqlMacroError> {
    let invalid = |reason: String| {
        SqlMacroError::new(
            INVALID_DEFINITION_CODE,
            format!(
                "body of macro {}() is not a valid {} macro: {reason}",
                definition.name,
                definition.form.label()
            ),
        )
    };
    let scanned: Vec<Token> =
        tokens(body).map_err(|_| invalid("it has an unclosed quote or comment".to_owned()))?;
    let references: Vec<ParameterReference> = parameter_references(body, &scanned);
    let parsed_body: ParsedBody =
        parsed(definition.form, &with_placeholders(body, &references)).map_err(invalid)?;
    if let Some(problem) = shape_problem(definition.form, &parsed_body.select) {
        return Err(invalid(problem.to_owned()));
    }
    let names: Vec<String> =
        defined_names(definition, &parsed_body.select, arguments).map_err(invalid)?;
    check_relation_values(definition, &parsed_body.select).map_err(|reason| {
        SqlMacroError::new(
            ARGUMENT_CODE,
            format!("macro {}(): {reason}", definition.name),
        )
    })?;
    let expanded: String = substituted_body(definition, (body, &scanned, &references), arguments);
    let sql: String = match definition.form {
        SqlMacroForm::Expression => expanded.trim().to_owned(),
        SqlMacroForm::CteList | SqlMacroForm::ColumnList => without_leading_keyword(&expanded),
    };
    Ok(BodyExpansion { sql, names })
}

/// `sql`, with a line break when it ends in a `--` comment and `followed` text would join that line.
pub(crate) fn with_line_comment_closed(sql: &str, followed: bool) -> String {
    let mut sql: String = sql.to_owned();
    if !followed {
        return sql;
    }
    let Ok(scanned) = tokens(&sql) else {
        return sql;
    };
    let mut rest: &str = &sql[scanned.last().map_or(0, |last| last.end)..];
    let mut open_line_comment: bool = false;
    loop {
        rest = rest.trim_start();
        if let Some(comment) = rest.strip_prefix("--") {
            match comment.split_once('\n') {
                Some((_, after)) => rest = after,
                None => {
                    open_line_comment = true;
                    break;
                }
            }
        } else if let Some(comment) = rest.strip_prefix("/*") {
            rest = comment.split_once("*/").map_or("", |(_, after)| after);
        } else {
            break;
        }
    }
    if open_line_comment {
        sql.push('\n');
    }
    sql
}

/// The text after its first token, the body's `WITH` or `SELECT`, trimmed.
fn without_leading_keyword(text: &str) -> String {
    match tokens(text) {
        Ok(scanned) => match scanned.first() {
            Some(first) => text[first.end..].trim().to_owned(),
            None => text.trim().to_owned(),
        },
        Err(_) => text.trim().to_owned(),
    }
}
