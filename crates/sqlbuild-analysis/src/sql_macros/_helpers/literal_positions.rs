//! Parameters a SQL macro body uses where SQL requires a literal, such as `LIMIT @n`.

use crate::sql_macros::_helpers::lexing::{Token, TokenKind, closing_token};
use crate::sql_macros::_helpers::parameters::ParameterReference;
use crate::sql_macros::constants::{
    LITERAL_REQUIRED_CODE, ROUND_FUNCTION, ROUND_PRECISION_ARGUMENT,
};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{ParameterKind, SqlMacroDefinition};

/// Adapters whose `ROUND` needs a literal precision (DuckDB for `DECIMAL` input, Spark SQL).
const LITERAL_ROUND_ADAPTERS: [&str; 3] = ["duckdb", "motherduck", "databricks"];
/// Adapters whose `DATE_TRUNC` takes its unit last, as `DATE_TRUNC(d, MONTH)`.
const UNIT_LAST_TRUNC_ADAPTERS: [&str; 1] = ["bigquery"];
const TRUNC_FUNCTIONS: [&str; 3] = ["DATE_TRUNC", "TIMESTAMP_TRUNC", "DATETIME_TRUNC"];

/// One parameter reference standing where a literal is required, and what requires it.
pub(crate) struct LiteralUse<'r> {
    pub(crate) reference: &'r ParameterReference,
    pub(crate) construct: &'static str,
}

/// Which positions need a literal: those every warehouse has, or the adapter's own too.
#[derive(Clone, Copy)]
pub(crate) enum LiteralRules<'a> {
    Universal,
    Adapter(&'a str),
}

/// The first reference to a runtime parameter that stands where SQL requires a literal.
pub(crate) fn non_literal_use<'r>(
    definition: &SqlMacroDefinition,
    scanned: &[Token],
    references: &'r [ParameterReference],
    rules: LiteralRules<'_>,
) -> Option<LiteralUse<'r>> {
    let body: &str = &definition.body;
    references.iter().find_map(|reference| {
        let parameter = definition.parameter(&reference.name)?;
        if !matches!(
            parameter.kind,
            ParameterKind::Expression { .. } | ParameterKind::Any | ParameterKind::ColumnOf { .. }
        ) {
            return None;
        }
        let at: usize = reference.token.checked_sub(1)?;
        let construct: &'static str = match rules {
            LiteralRules::Universal => universal_construct(body, scanned, at),
            LiteralRules::Adapter(adapter) => adapter_construct(body, scanned, at, adapter),
        }?;
        Some(LiteralUse {
            reference,
            construct,
        })
    })
}

/// `LIMIT`, `OFFSET`, `TOP`, `FETCH FIRST`, an `INTERVAL` or `EXTRACT` unit, or `PIVOT ... IN`.
fn universal_construct(body: &str, scanned: &[Token], at: usize) -> Option<&'static str> {
    let before = |back: usize| at.checked_sub(back).map(|index| &scanned[index]);
    if let Some(previous) = before(1) {
        for keyword in ["LIMIT", "OFFSET", "TOP"] {
            if previous.is_word(body, keyword) {
                return Some(keyword);
            }
        }
        if (previous.is_word(body, "FIRST") || previous.is_word(body, "NEXT"))
            && before(2).is_some_and(|fetch| fetch.is_word(body, "FETCH"))
        {
            return Some("FETCH FIRST");
        }
        if previous.is(body, "(") && before(2).is_some_and(|word| word.is_word(body, "EXTRACT")) {
            return Some("an EXTRACT unit");
        }
        if interval_value_ends_at(body, scanned, at - 1) {
            return Some("an INTERVAL unit");
        }
    }
    if in_pivot_values(body, scanned, at) {
        return Some("PIVOT ... IN values");
    }
    None
}

/// `ROUND` precision and the `DATE_TRUNC` unit, where the adapter needs a literal for them.
fn adapter_construct(
    body: &str,
    scanned: &[Token],
    at: usize,
    adapter: &str,
) -> Option<&'static str> {
    let (function, argument, count) = enclosing_call(body, scanned, at)?;
    let upper: String = function.to_ascii_uppercase();
    if upper == ROUND_FUNCTION
        && argument == ROUND_PRECISION_ARGUMENT
        && LITERAL_ROUND_ADAPTERS.contains(&adapter)
    {
        return Some("ROUND precision");
    }
    if TRUNC_FUNCTIONS.contains(&upper.as_str()) {
        let unit: usize = if UNIT_LAST_TRUNC_ADAPTERS.contains(&adapter) {
            count - 1
        } else {
            0
        };
        if argument == unit && count > 1 {
            return Some("a DATE_TRUNC unit");
        }
    }
    None
}

/// Whether the token at `end` closes the value of an `INTERVAL <value>`, so a unit follows.
fn interval_value_ends_at(body: &str, scanned: &[Token], end: usize) -> bool {
    let value: &Token = &scanned[end];
    let start: Option<usize> = match value.kind {
        TokenKind::Text | TokenKind::Number => Some(end),
        TokenKind::Word if end > 0 && scanned[end - 1].is(body, "@") => Some(end - 1),
        TokenKind::Punct if value.is(body, ")") => opening_token(body, scanned, end),
        _ => None,
    };
    start
        .and_then(|start| start.checked_sub(1))
        .is_some_and(|keyword| scanned[keyword].is_word(body, "INTERVAL"))
}

/// The index of the bracket token `close` closes.
fn opening_token(body: &str, scanned: &[Token], close: usize) -> Option<usize> {
    let mut depth: usize = 0;
    for index in (0..=close).rev() {
        let token: &Token = &scanned[index];
        if token.kind != TokenKind::Punct {
            continue;
        }
        match token.text(body) {
            ")" | "]" | "}" => depth += 1,
            "(" | "[" | "{" => {
                depth -= 1;
                if depth == 0 {
                    return Some(index);
                }
            }
            _ => {}
        }
    }
    None
}

/// The function whose arguments hold token `at`, the argument's index and the argument count.
fn enclosing_call<'b>(
    body: &'b str,
    scanned: &[Token],
    at: usize,
) -> Option<(&'b str, usize, usize)> {
    let mut depth: usize = 0;
    let mut commas: usize = 0;
    for index in (0..at).rev() {
        let token: &Token = &scanned[index];
        if token.kind != TokenKind::Punct {
            continue;
        }
        match token.text(body) {
            ")" | "]" | "}" => depth += 1,
            "(" | "[" | "{" if depth > 0 => depth -= 1,
            "(" => {
                let function: &Token = scanned.get(index.checked_sub(1)?)?;
                if function.kind != TokenKind::Word {
                    return None;
                }
                let close: usize = closing_token(body, scanned, index)?;
                let count: usize = 1 + top_level_commas(body, &scanned[index + 1..close]);
                return Some((function.text(body), commas, count));
            }
            "," if depth == 0 => commas += 1,
            _ => {}
        }
    }
    None
}

fn top_level_commas(body: &str, tokens: &[Token]) -> usize {
    let mut depth: usize = 0;
    let mut commas: usize = 0;
    for token in tokens {
        if token.kind != TokenKind::Punct {
            continue;
        }
        match token.text(body) {
            "(" | "[" | "{" => depth += 1,
            ")" | "]" | "}" => depth = depth.saturating_sub(1),
            "," if depth == 0 => commas += 1,
            _ => {}
        }
    }
    commas
}

/// Whether token `at` is one of the values of the first `IN (...)` after a `PIVOT`.
fn in_pivot_values(body: &str, scanned: &[Token], at: usize) -> bool {
    for (pivot, token) in scanned[..at].iter().enumerate() {
        if !token.is_word(body, "PIVOT") {
            continue;
        }
        let Some(keyword) = scanned[pivot + 1..at]
            .iter()
            .position(|word| word.is_word(body, "IN"))
            .map(|offset| pivot + 1 + offset)
        else {
            continue;
        };
        let open: usize = keyword + 1;
        if !scanned.get(open).is_some_and(|token| token.is(body, "(")) {
            continue;
        }
        if let Some(close) = closing_token(body, scanned, open)
            && open < at
            && at < close
        {
            return true;
        }
    }
    false
}

/// The error for a runtime parameter standing where a literal is required.
pub(crate) fn literal_error(
    definition: &SqlMacroDefinition,
    found: &LiteralUse<'_>,
) -> SqlMacroError {
    let name: &str = &found.reference.name;
    let help: String = match definition.parameter(name).map(|parameter| &parameter.kind) {
        Some(ParameterKind::Expression { data_type }) => {
            format!("declare it {name} {data_type} CONST")
        }
        Some(ParameterKind::Any) => {
            format!("declare it with a type and CONST, such as {name} VARCHAR CONST")
        }
        _ => format!("pass the value through a CONST argument, such as {name}_value VARCHAR CONST"),
    };
    SqlMacroError::new(LITERAL_REQUIRED_CODE, format!("{name} is used where a literal is required; {help}"))
        .helped(format!(
            "macro {}() uses @{name} as {}, which SQL accepts only as a literal; a CONST argument takes only values known at compile time",
            definition.name, found.construct
        ))
}
