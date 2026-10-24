//! A CTE-list macro body's CTEs renamed for one call's `__cte` name, located by parsing.

use polyglot_sql::expressions::Identifier;
use polyglot_sql::{DialectType, Expression, ExpressionWalk};

use crate::sql_macros::_helpers::lexing::{Token, tokens};
use crate::sql_macros::_helpers::parameters::{
    ParameterReference, parameter_references, placeholder, with_placeholders,
};
use crate::sql_macros::_helpers::typed_calls::spliced;
use crate::sql_macros::constants::{ARGUMENT_CODE, CTE_ARGUMENT, CTE_NAME_SEPARATOR};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{
    CallArgument, ExpandedText, SqlMacroDefinition, SqlMacroForm, TextSplice,
};

/// Dialects tried in turn to parse a body for its CTE names.
const PARSE_DIALECTS: [DialectType; 4] = [
    DialectType::Generic,
    DialectType::DuckDB,
    DialectType::Snowflake,
    DialectType::BigQuery,
];
/// The query a CTE list is completed with to parse it.
const CTE_SUFFIX: &str = "\nSELECT 1";

/// The call's `__cte` name, removed from its arguments, or why it cannot be used.
pub(crate) fn take_cte_argument(
    definition: &SqlMacroDefinition,
    arguments: Vec<CallArgument>,
) -> Result<(Option<String>, Vec<CallArgument>), SqlMacroError> {
    let mut name: Option<String> = None;
    let mut kept: Vec<CallArgument> = Vec::with_capacity(arguments.len());
    for argument in arguments {
        if !argument
            .name
            .as_deref()
            .is_some_and(|named| named.eq_ignore_ascii_case(CTE_ARGUMENT))
        {
            kept.push(argument);
            continue;
        }
        if definition.form != SqlMacroForm::CteList {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!(
                    "{CTE_ARGUMENT} names the CTEs a CTE-list macro inserts; {}() is {} {} macro",
                    definition.name,
                    if definition.form == SqlMacroForm::Expression {
                        "an"
                    } else {
                        "a"
                    },
                    definition.form.label()
                ),
            )
            .helped(format!("remove {CTE_ARGUMENT} := {}", argument.text.trim())));
        }
        if name.is_some() {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!(
                    "{CTE_ARGUMENT} is passed twice in a call to macro {}()",
                    definition.name
                ),
            ));
        }
        let text: &str = argument.text.trim();
        if !is_bare_identifier(text) {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!(
                    "{CTE_ARGUMENT} of macro {}() must be a bare CTE name; got {text}",
                    definition.name
                ),
            )
            .helped(format!("pass a name such as {CTE_ARGUMENT} := eu_orders")));
        }
        name = Some(text.to_owned());
    }
    Ok((name, kept))
}

/// Whether `text` is one unquoted identifier.
fn is_bare_identifier(text: &str) -> bool {
    let mut characters = text.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

/// The name each of a body's CTEs takes: the last takes `name`, the others `<name>__<cte>`.
fn renamed(ctes: &[String], name: &str, cte: &str) -> Option<String> {
    let index: usize = ctes
        .iter()
        .position(|defined| defined.eq_ignore_ascii_case(cte))?;
    Some(if index + 1 == ctes.len() {
        name.to_owned()
    } else {
        format!("{name}{CTE_NAME_SEPARATOR}{}", ctes[index])
    })
}

/// `body` with every CTE it defines, and every reference to one, renamed for `name`.
pub(crate) fn renamed_ctes(body: &ExpandedText, name: &str) -> Result<ExpandedText, String> {
    let sql: &str = &body.sql;
    let scanned: Vec<Token> =
        tokens(sql).map_err(|_| "it has an unclosed quote or comment".to_owned())?;
    let references: Vec<ParameterReference> = parameter_references(sql, &scanned);
    let parsed_text: String = format!("{}{CTE_SUFFIX}", with_placeholders(sql, &references));
    let statement: Expression = parsed(&parsed_text)?;
    let Expression::Select(select) = &statement else {
        return Err("it is not a WITH list".to_owned());
    };
    let Some(with) = &select.with else {
        return Err("it is not a WITH list".to_owned());
    };
    let ctes: Vec<String> = with.ctes.iter().map(|cte| cte.alias.name.clone()).collect();
    let aliases: Vec<String> = statement
        .dfs()
        .filter_map(|node| match node {
            Expression::Table(table) => table.alias.as_ref().map(|alias| alias.name.clone()),
            _ => None,
        })
        .collect();
    let mut identifiers: Vec<&Identifier> = with.ctes.iter().map(|cte| &cte.alias).collect();
    for node in statement.dfs() {
        match node {
            Expression::Table(table) if table.schema.is_none() && table.catalog.is_none() => {
                identifiers.push(&table.name);
            }
            Expression::Column(column) => identifiers.extend(column.table.as_ref()),
            Expression::Star(star) => identifiers.extend(star.table.as_ref()),
            _ => {}
        }
    }
    let shadowed = |identifier: &Identifier| {
        aliases
            .iter()
            .any(|alias| alias.eq_ignore_ascii_case(&identifier.name))
    };
    let offsets: CharOffsets = CharOffsets::new(&parsed_text);
    let mut edits: Vec<(usize, usize, String)> = Vec::new();
    for (position, identifier) in identifiers.into_iter().enumerate() {
        let is_definition: bool = position < with.ctes.len();
        let Some(new_name) = renamed(&ctes, name, &identifier.name) else {
            continue;
        };
        if !is_definition && shadowed(identifier) {
            continue;
        }
        let Some(span) = identifier.span else {
            continue;
        };
        let start: usize = original_offset(offsets.byte(span.start), sql, &references);
        let end: usize = original_offset(offsets.byte(span.end), sql, &references);
        let text: String = if identifier.quoted {
            format!("\"{new_name}\"")
        } else {
            new_name
        };
        edits.push((start, end, text));
    }
    edits.sort_by_key(|(start, _, _)| *start);
    edits.dedup_by_key(|(start, _, _)| *start);
    let mut renamed_sql: String = String::with_capacity(sql.len() + edits.len() * name.len());
    let mut splices: Vec<TextSplice> = Vec::with_capacity(edits.len());
    let mut cursor: usize = 0;
    for (start, end, text) in edits {
        if start < cursor || end > sql.len() {
            continue;
        }
        renamed_sql.push_str(&sql[cursor..start]);
        let output: usize = renamed_sql.len();
        renamed_sql.push_str(&text);
        splices.push(TextSplice {
            source: (start, end),
            output: (output, renamed_sql.len()),
        });
        cursor = end;
    }
    renamed_sql.push_str(&sql[cursor..]);
    Ok(ExpandedText {
        calls: spliced(body.calls.clone(), &splices),
        sql: renamed_sql,
    })
}

/// The one statement `text` parses to, in the first dialect that parses it.
fn parsed(text: &str) -> Result<Expression, String> {
    let mut first_error: Option<String> = None;
    for dialect in PARSE_DIALECTS {
        match polyglot_sql::parse(text, dialect) {
            Ok(mut statements) if statements.len() == 1 => {
                if let Some(statement) = statements.pop() {
                    return Ok(statement);
                }
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

/// The byte offset in `sql` of byte `offset` of `sql` with its references as placeholders.
fn original_offset(offset: usize, sql: &str, references: &[ParameterReference]) -> usize {
    let mut moved: isize = 0;
    for reference in references {
        let placed_start: isize = reference.start as isize + moved;
        if (offset as isize) <= placed_start {
            break;
        }
        moved += placeholder(&reference.name).len() as isize
            - (reference.end - reference.start) as isize;
    }
    usize::try_from(offset as isize - moved)
        .unwrap_or(0)
        .min(sql.len())
}

/// Byte offsets of a text's character offsets.
struct CharOffsets {
    bytes: Option<Vec<usize>>,
}

impl CharOffsets {
    fn new(text: &str) -> Self {
        if text.is_ascii() {
            return Self { bytes: None };
        }
        let mut bytes: Vec<usize> = text.char_indices().map(|(offset, _)| offset).collect();
        bytes.push(text.len());
        Self { bytes: Some(bytes) }
    }

    fn byte(&self, character: usize) -> usize {
        match &self.bytes {
            Some(bytes) => bytes.get(character).copied().unwrap_or(character),
            None => character,
        }
    }
}
