//! SQLBuild codes and dialect-specific diagnostic evidence.

use crate::semantic_validation::_helpers::catalog::diagnostic_row;
use crate::semantic_validation::types::DiagnosticRow;
use polyglot_sql::expressions::Select;
use polyglot_sql::{
    Dialect, DialectType, Expression, ExpressionWalk, ValidationError, ValidationResult,
    ValidationSeverity,
};
use regex::Regex;
use std::collections::HashSet;
use std::sync::LazyLock;

const UNKNOWN_COLUMN: &str = "E201";
const ORDER_BY: &str = "ORDER BY";
const ERROR: &str = "error";
static COLUMN: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    Regex::new(r"(?:Unknown column|Ambiguous column reference|JOIN USING column) '([^']+)'")
        .map_err(|error| error.to_string())
});
static ALIAS: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    Regex::new(r"^(?:Unknown column '([^']+)'(?: in table '[^']+'| \(not found in any referenced table\))|Ambiguous unqualified column '([^']+)' found in [0-9]+ referenced tables)$").map_err(|error| error.to_string())
});
static VALUES: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    Regex::new(r"(?i)^Unknown column '(column([1-9][0-9]*))'$").map_err(|error| error.to_string())
});
static CONTEXTS: LazyLock<Result<Vec<(&str, Regex)>, String>> = LazyLock::new(|| {
    [
        ("JOIN USING", r"\bUSING\s*\("),
        ("QUALIFY", r"\bQUALIFY\b"),
        ("HAVING", r"\bHAVING\b"),
        ("GROUP BY", r"\bGROUP\s+BY\b"),
        (ORDER_BY, r"\bORDER\s+BY\b"),
        ("WINDOW PARTITION BY", r"\bPARTITION\s+BY\b"),
        ("JOIN ON", r"\bON\b"),
        ("WHERE", r"\bWHERE\b"),
        ("SELECT", r"\bSELECT\b"),
    ]
    .into_iter()
    .map(compile_context)
    .collect()
});

fn compile_context(
    (label, pattern): (&'static str, &'static str),
) -> Result<(&'static str, Regex), String> {
    Ok((
        label,
        Regex::new(&format!("(?i){pattern}")).map_err(|error| error.to_string())?,
    ))
}

pub(crate) fn column_pattern() -> Result<&'static Regex, String> {
    COLUMN.as_ref().map_err(Clone::clone)
}

struct DiagnosticContext<'a> {
    sql: &'a str,
    dialect: DialectType,
    statements: Option<Vec<Expression>>,
}

impl DiagnosticContext<'_> {
    fn map(&mut self, mut error: ValidationError) -> Result<Option<ValidationError>, String> {
        if error.code.starts_with('B') {
            return Ok(Some(error));
        }
        let Some(code) = sqlbuild_code(&error.code) else {
            return Ok(None);
        };
        if let Some(start) = error.start {
            (error.line, error.column) = line_column(self.sql, start);
        }
        if self.dialect == DialectType::Snowflake
            && (VALUES
                .as_ref()
                .map_err(Clone::clone)?
                .is_match(&error.message)
                || ALIAS
                    .as_ref()
                    .map_err(Clone::clone)?
                    .is_match(&error.message))
        {
            let expressions = self.statements.get_or_insert_with(|| {
                match Dialect::get(self.dialect).parse(self.sql) {
                    Ok(expressions) => expressions,
                    Err(_) => Vec::new(),
                }
            });
            for expression in expressions {
                for node in expression.dfs() {
                    if let Expression::Select(select) = node
                        && select_proves(select, &error)?
                    {
                        return Ok(None);
                    }
                }
            }
        }
        if let Some(captures) = column_pattern()?.captures(&error.message) {
            let name = captures[1].rsplit('.').next().unwrap_or(&captures[1]);
            let occurrences = occurrences(self.sql, name);
            if let Some(&first) = occurrences.first() {
                if error.line.is_none() && occurrences.len() == 1 {
                    (error.line, error.column) =
                        line_column(self.sql, self.sql[..first].chars().count());
                }
                if let Some(context) = context(&self.sql[..first])? {
                    error.message.push_str(&format!(" (context: {context})"));
                }
            }
        }
        error.code = code;
        Ok(Some(error))
    }
}

pub(crate) fn map_diagnostics(
    sql: &str,
    dialect: DialectType,
    result: ValidationResult,
) -> Result<ValidationResult, String> {
    let mut context = DiagnosticContext {
        sql,
        dialect,
        statements: None,
    };
    let mut errors: Vec<ValidationError> = Vec::with_capacity(result.errors.len());
    for error in result.errors {
        if let Some(error) = context.map(error)? {
            errors.push(error);
        }
    }
    let valid = !errors
        .iter()
        .any(|error| error.severity == ValidationSeverity::Error);
    Ok(ValidationResult { valid, errors })
}

fn sqlbuild_code(code: &str) -> Option<String> {
    let direct = match code {
        "E001" | "E002" | "E003" | "E004" | "E200" => Some("B000"),
        "E201" => Some("B002"),
        "E221" => Some("B003"),
        "E222" => Some("B004"),
        "E223" => Some("B005"),
        "E202" => Some("B101"),
        "E203" => Some("B102"),
        _ => None,
    };
    if let Some(code) = direct {
        return Some(code.to_owned());
    }
    let number = match code.get(1..)?.parse::<usize>() {
        Ok(number) => number,
        Err(_) => return None,
    };
    if code.starts_with('E') && ((210..=219).contains(&number) || (230..=234).contains(&number)) {
        return Some(format!("B{number}"));
    }
    (code.starts_with('W') && (210..=219).contains(&number)).then(|| code.to_owned())
}

fn occurrences(sql: &str, name: &str) -> Vec<usize> {
    sql.match_indices(name)
        .filter_map(|(offset, _)| {
            let word = |ch: char| ch.is_ascii_alphanumeric() || ch == '_';
            (!sql[..offset].chars().next_back().is_some_and(word)
                && !sql[offset + name.len()..].chars().next().is_some_and(word))
            .then_some(offset)
        })
        .collect()
}

fn context(prefix: &str) -> Result<Option<&'static str>, String> {
    let mut latest = None;
    for (label, pattern) in CONTEXTS.as_ref().map_err(Clone::clone)? {
        if let Some(found) = pattern.find_iter(prefix).last()
            && latest.is_none_or(|(start, _)| found.start() > start)
        {
            latest = Some((found.start(), *label));
        }
    }
    let Some((start, label)) = latest else {
        return Ok(None);
    };
    if label == ORDER_BY
        && let Some(over) = prefix.to_ascii_uppercase().rfind("OVER")
        && (over > start
            || prefix[over..].matches('(').count() > prefix[over..].matches(')').count())
    {
        return Ok(Some("WINDOW ORDER BY"));
    }
    Ok(Some(label))
}

fn line_column(sql: &str, offset: usize) -> (Option<usize>, Option<usize>) {
    let mut line = 1;
    let mut column = 1;
    for ch in sql.chars().take(offset) {
        if ch == '\n' {
            line += 1;
            column = 1;
        } else {
            column += 1;
        }
    }
    (Some(line), Some(column))
}

fn unqualified(expression: &Expression, name: &str) -> bool {
    if let Expression::Column(column) = expression {
        return column.table.is_none()
            && !column.name.quoted
            && column.name.name.eq_ignore_ascii_case(name);
    }
    if matches!(expression, Expression::Select(_)) {
        return false;
    }
    expression
        .children()
        .iter()
        .any(|child| unqualified(child, name))
}

fn select_proves(select: &Select, error: &ValidationError) -> Result<bool, String> {
    if let Some(captures) = VALUES
        .as_ref()
        .map_err(Clone::clone)?
        .captures(&error.message)
    {
        let ordinal = match captures[2].parse::<usize>() {
            Ok(ordinal) => ordinal,
            Err(_) => return Ok(false),
        };
        if !select.joins.is_empty() {
            return Ok(false);
        }
        let Some(from) = &select.from else {
            return Ok(false);
        };
        let [Expression::Values(values)] = from.expressions.as_slice() else {
            return Ok(false);
        };
        if values.alias.is_some()
            || !values.column_aliases.is_empty()
            || values.expressions.is_empty()
            || values
                .expressions
                .iter()
                .any(|row| row.expressions.len() < ordinal)
        {
            return Ok(false);
        }
        for projection in &select.expressions {
            let value = match projection {
                Expression::Alias(alias) => &alias.this,
                other => other,
            };
            if let Expression::Column(column) = value
                && column.table.is_none()
                && !column.name.quoted
                && column.name.name.eq_ignore_ascii_case(&captures[1])
                && column.span.is_some_and(|span| {
                    Some(span.line) == error.line && Some(span.column) == error.column
                })
            {
                return Ok(true);
            }
        }
        return Ok(false);
    }
    let Some(captures) = ALIAS
        .as_ref()
        .map_err(Clone::clone)?
        .captures(&error.message)
    else {
        return Ok(false);
    };
    let Some(name) = captures
        .get(1)
        .or_else(|| captures.get(2))
        .map(|name| name.as_str().to_ascii_lowercase())
    else {
        return Ok(false);
    };
    let mut aliases: HashSet<String> = HashSet::new();
    for projection in &select.expressions {
        let (expression, alias) = match projection {
            Expression::Alias(alias) => (
                &alias.this,
                (!alias.alias.quoted).then_some(alias.alias.name.to_ascii_lowercase()),
            ),
            other => (other, None),
        };
        if error.code == UNKNOWN_COLUMN && aliases.contains(&name) && unqualified(expression, &name)
        {
            return Ok(true);
        }
        if let Some(alias) = alias {
            aliases.insert(alias);
        }
    }
    if !aliases.contains(&name) {
        return Ok(false);
    }
    if error.code == UNKNOWN_COLUMN {
        return Ok(select
            .where_clause
            .as_ref()
            .is_some_and(|clause| unqualified(&clause.this, &name)));
    }
    Ok(select.order_by.as_ref().is_some_and(|order| {
        order
            .expressions
            .iter()
            .any(|ordered| unqualified(&ordered.this, &name))
    }))
}

pub(crate) fn binding_diagnostics(
    sql: &str,
    dialect: &str,
    rows: Vec<DiagnosticRow>,
) -> Result<Vec<DiagnosticRow>, String> {
    let errors: Vec<ValidationError> = rows
        .into_iter()
        .map(
            |(code, message, line, column, start, end, severity)| ValidationError {
                code,
                message,
                line,
                column,
                start,
                end,
                severity: if severity == ERROR {
                    ValidationSeverity::Error
                } else {
                    ValidationSeverity::Warning
                },
            },
        )
        .collect();
    let result = map_diagnostics(
        sql,
        dialect.parse().map_err(|error| format!("{error}"))?,
        ValidationResult {
            valid: false,
            errors,
        },
    )?;
    Ok(result.errors.into_iter().map(diagnostic_row).collect())
}
