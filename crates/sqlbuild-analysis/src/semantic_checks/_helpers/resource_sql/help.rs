//! Python's `resource_sql_help`: a concrete fix quoting the authored span of a finding.

use std::collections::BTreeSet;
use std::sync::LazyLock;

use regex::Regex;
use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::semantic_checks::_helpers::explanation::columns::closest_column;
use crate::semantic_checks::_helpers::explanation::messages::{missing_column, pattern};
use crate::semantic_checks::_helpers::sql_text::patterns::{compile_pattern, ignorecase_word};
use crate::semantic_checks::_helpers::sql_text::text::{casefold, upper};
use crate::semantic_checks::models::{ResourceSqlKind, SemanticFailure};

const SET_OPERATION_CODE: &str = "B215";
const COMPARISON_CODE: &str = "B217";
const UNKNOWN_COLUMN_CODE: &str = "B002";
const SNOWFLAKE: &str = "snowflake";
const RELATION_PARAMETER: &str = "@relation";
const LISTED_COLUMNS: usize = 10;
const TEXT_TYPES: [&str; 4] = ["VARCHAR", "STRING", "TEXT", "CHAR"];
const TEMPORAL_TYPES: [&str; 2] = ["TIMESTAMP", "DATE"];
const SET_OPERATION_KEYWORDS: [&str; 10] = [
    "UNION",
    "ALL",
    "EXCEPT",
    "INTERSECT",
    "MINUS",
    "SELECT",
    "FROM",
    "DISTINCT",
    "BY",
    "NAME",
];
const TYPE_WORD: &str = r"(?:{W}|[()])+";
const NAME_TAIL: &str = r"(?:{W}|\$)*";

static SET_OPERATION_TYPES: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    compile_pattern(&format!(
        r"{} (?P<position>{{D}}+).*{} {} (?P<left>{TYPE_WORD}), {} {} (?P<right>{TYPE_WORD})",
        ignorecase_word("column"),
        ignorecase_word("accumulated"),
        ignorecase_word("type"),
        ignorecase_word("next"),
        ignorecase_word("type"),
    ))
});
static COMPARISON_TYPES: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    compile_pattern(&format!(
        r"{} (?P<left>{TYPE_WORD}) {} (?P<right>{TYPE_WORD})",
        ignorecase_word("between"),
        ignorecase_word("and"),
    ))
});
static ALIAS_NAME: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    compile_pattern(&format!(
        r#"{{S}}+{}{{S}}+"?(?P<name>{{L}}{NAME_TAIL})"?,?\z"#,
        ignorecase_word("AS")
    ))
});
static CAST: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    compile_pattern(&format!(
        r"\A{}\((?P<inner>.+){{S}}+{}{{S}}+(?:{{W}}|[(), ])+\)\z",
        ignorecase_word("CAST"),
        ignorecase_word("AS")
    ))
});
static SINGLE_OPERAND: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    compile_pattern(&format!(
        r"\A(?:'(?:[^']|'')*'|[A-Za-z_]{NAME_TAIL}(?:\.[A-Za-z_]{NAME_TAIL})?)\z"
    ))
});
static PARAMETER: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compile_pattern(r"@[A-Za-z_]{W}*"));

/// What one finding's help reads besides its code and message.
pub(crate) struct HelpContext<'a> {
    pub(crate) kind: ResourceSqlKind,
    pub(crate) authored_text: &'a str,
    pub(crate) authored_line: &'a str,
    pub(crate) column: i64,
    pub(crate) authored_body: &'a str,
    pub(crate) audit_definition: Option<&'a str>,
    pub(crate) shapes: &'a [(String, Vec<(String, String)>)],
    pub(crate) relations: &'a BTreeSet<String>,
    pub(crate) dialect: Option<&'a str>,
}

fn is_text(value: &str) -> bool {
    TEXT_TYPES.iter().any(|kind| value.starts_with(kind))
}

fn temporal_type(types: &[String; 2]) -> Option<&'static str> {
    for value in types {
        for kind in TEMPORAL_TYPES {
            if value.starts_with(kind) {
                return Some(kind);
            }
        }
    }
    None
}

fn shape<'a>(shapes: &'a [(String, Vec<(String, String)>)], name: &str) -> &'a [(String, String)] {
    shapes
        .iter()
        .find(|(shape, _)| shape == name)
        .map_or(&[], |(_, columns)| columns.as_slice())
}

/// Python's `resource_sql_help`, or None to keep the generic help.
pub(crate) fn resource_sql_help(
    code: &str,
    message: &str,
    context: &HelpContext<'_>,
) -> Result<Option<String>, SemanticFailure> {
    if code == SET_OPERATION_CODE {
        return set_operation_help(message, context);
    }
    if code == COMPARISON_CODE && context.kind == ResourceSqlKind::Audit {
        return audit_comparison_help(message, context);
    }
    if code == UNKNOWN_COLUMN_CODE && context.kind == ResourceSqlKind::SqlTest {
        return unknown_column_help(message, context.shapes);
    }
    Ok(None)
}

fn code_points(text: &str, start: usize, end: usize) -> String {
    text.chars()
        .skip(start)
        .take(end.saturating_sub(start))
        .collect()
}

/// Python's `_set_operation_operand`.
fn set_operation_operand(
    context: &HelpContext<'_>,
    position: &str,
) -> Result<String, SemanticFailure> {
    let preceding = if context.column > 1 {
        let index = (context.column - 2) as usize;
        code_points(context.authored_line, index, index + 1)
    } else {
        String::new()
    };
    let stripped = str::trim(context.authored_text).trim_end_matches(',');
    let alias = pattern(&ALIAS_NAME)?;
    let mut expression: String = alias.replace_all(stripped, "").into_owned();
    if let Some(captures) = pattern(&CAST)?.captures(&expression) {
        expression = str::trim(&captures["inner"]).to_owned();
    }
    let preceding_is_word = preceding
        .chars()
        .next()
        .is_some_and(|character| character == '$' || is_word_char(character));
    if !preceding_is_word
        && pattern(&SINGLE_OPERAND)?.is_match(&expression)
        && !SET_OPERATION_KEYWORDS.contains(&upper(&expression).as_str())
    {
        return Ok(expression);
    }
    Ok(format!("COLUMN{position}"))
}

/// Python's `_model_type`: the tested relation's type for the branch column, when one matches.
fn model_type(context: &HelpContext<'_>, operand: &str) -> Result<Option<String>, SemanticFailure> {
    let mut names: Vec<String> = Vec::new();
    if let Some(captures) = pattern(&ALIAS_NAME)?.captures(str::trim(context.authored_text)) {
        names.push(captures["name"].to_owned());
    }
    names.push(
        operand
            .rsplit('.')
            .next()
            .unwrap_or(operand)
            .trim_matches('"')
            .to_owned(),
    );
    for name in names {
        let folded = casefold(&name);
        let mut found: BTreeSet<String> = BTreeSet::new();
        for relation in context.relations {
            for (output, value) in shape(context.shapes, relation) {
                if casefold(output) == folded && !value.is_empty() {
                    found.insert(upper(value.split('(').next().unwrap_or(value)));
                }
            }
        }
        if found.len() == 1 {
            return Ok(found.into_iter().next());
        }
    }
    Ok(None)
}

fn set_operation_help(
    message: &str,
    context: &HelpContext<'_>,
) -> Result<Option<String>, SemanticFailure> {
    let Some(captures) = pattern(&SET_OPERATION_TYPES)?.captures(message) else {
        return Ok(None);
    };
    let position = &captures["position"];
    let left = upper(&captures["left"]);
    let right = upper(&captures["right"]);
    let column = set_operation_operand(context, position)?;
    if context.kind != ResourceSqlKind::SqlTest {
        return Ok(Some(format!(
            "Cast one branch so both branches have the same type, for example \
             `CAST({column} AS {left})` for set-operation column {position}"
        )));
    }
    if let Some(model_type) = model_type(context, &column)? {
        return Ok(Some(format!(
            "Cast set-operation column {position} to the tested model's type {model_type} in \
             the expected or fixture rows, for example `CAST({column} AS {model_type})`"
        )));
    }
    let target = if is_text(&left) && !is_text(&right) {
        right
    } else {
        left
    };
    Ok(Some(format!(
        "Cast set-operation column {position} explicitly so every branch has the same type, \
         for example `CAST({column} AS {target})` in the expected or fixture rows"
    )))
}

/// Python's `_audit_parameter`: the parameter nearest the finding on its line, else the only one.
fn audit_parameter(context: &HelpContext<'_>) -> Result<String, SemanticFailure> {
    let parameters = pattern(&PARAMETER)?;
    let line = context.authored_line;
    let nearest = parameters
        .find_iter(line)
        .filter(|found| found.as_str() != RELATION_PARAMETER)
        .map(|found| {
            let start = line[..found.start()].chars().count() as i64;
            ((start + 1 - context.column).abs(), found.as_str())
        })
        .fold(None::<(i64, &str)>, |best, candidate| match best {
            Some(current) if current.0 <= candidate.0 => Some(current),
            _ => Some(candidate),
        });
    if let Some((_, parameter)) = nearest {
        return Ok(parameter.to_owned());
    }
    let unique: BTreeSet<&str> = parameters
        .find_iter(context.authored_body)
        .map(|found| found.as_str())
        .filter(|found| *found != RELATION_PARAMETER)
        .collect();
    Ok(match unique.into_iter().collect::<Vec<_>>().as_slice() {
        [only] => (*only).to_owned(),
        _ => "<text expression>".to_owned(),
    })
}

fn audit_comparison_help(
    message: &str,
    context: &HelpContext<'_>,
) -> Result<Option<String>, SemanticFailure> {
    let Some(captures) = pattern(&COMPARISON_TYPES)?.captures(message) else {
        return Ok(None);
    };
    let types = [upper(&captures["left"]), upper(&captures["right"])];
    let Some(temporal) = temporal_type(&types) else {
        return Ok(None);
    };
    if !types.iter().any(|value| is_text(value)) {
        return Ok(None);
    }
    let operand = audit_parameter(context)?;
    let conversion = if context.dialect == Some(SNOWFLAKE) {
        format!("TO_{temporal}({operand})")
    } else {
        format!("CAST({operand} AS {temporal})")
    };
    let audit = match context.audit_definition.filter(|name| !name.is_empty()) {
        Some(name) => format!("audit '{name}'"),
        None => "the audit".to_owned(),
    };
    Ok(Some(format!(
        "Convert the text value explicitly, for example `{conversion}`, or attach {audit} to a \
         {temporal} column"
    )))
}

fn unknown_column_help(
    message: &str,
    shapes: &[(String, Vec<(String, String)>)],
) -> Result<Option<String>, SemanticFailure> {
    let Some((name, Some(table))) = missing_column(message)? else {
        return Ok(None);
    };
    let columns = shape(shapes, &table);
    if let Some(suggestion) = closest_column(&name, columns)? {
        return Ok(Some(format!("did you mean '{suggestion}'?")));
    }
    let listed: Vec<&str> = columns
        .iter()
        .take(LISTED_COLUMNS)
        .map(|(column, _)| column.as_str())
        .collect();
    let more = if columns.len() > LISTED_COLUMNS {
        format!(", and {} more", columns.len() - LISTED_COLUMNS)
    } else {
        String::new()
    };
    let outputs = if columns.is_empty() {
        String::new()
    } else {
        format!(" (it outputs {}{more})", listed.join(", "))
    };
    Ok(Some(format!(
        "'{table}' does not output '{name}'{outputs}; update the test to its current columns"
    )))
}
