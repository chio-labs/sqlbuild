use polyglot_sql::DialectType;
use polyglot_sql::tokens::{Token, TokenType};

use crate::sql_lint::_helpers::engine::{is_comment, is_layout};
use crate::sql_lint::constants::MAX_TSQL_LITERAL_BYTES;
use crate::sql_lint::models::{LintDiagnostic, LintEdit, LintRuleMetadata, LiteralContext};

pub(super) const LONG_LITERAL: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL044",
    message: "String literal exceeds max_literal_length",
    remediation: "Split the value into shorter concatenated literals with format --fix, or move the value to a seed or a macro.",
};

pub(crate) fn default_limit() -> usize {
    100
}

pub(super) fn diagnostics(context: LiteralContext<'_>) -> Vec<LintDiagnostic> {
    let LiteralContext {
        sql,
        tokens,
        limit,
        header,
        ..
    } = context;
    let characters: Vec<char> = sql.chars().collect();
    tokens
        .iter()
        .enumerate()
        .filter_map(|(index, token)| {
            if !(is_string(token.token_type)
                || header
                    && matches!(
                        token.token_type,
                        TokenType::Identifier | TokenType::QuotedIdentifier
                    ))
                || token.text.chars().count() <= limit
            {
                return None;
            }
            let source: String = characters
                .get(token.span.start..token.span.end)?
                .iter()
                .collect();
            if header
                && matches!(
                    token.token_type,
                    TokenType::Identifier | TokenType::QuotedIdentifier
                )
                && !source.starts_with('"')
            {
                return None;
            }
            let result = replacement(&source, token, index, &context);
            let (fix, reason) = match result {
                Ok(replacement) => (
                    Some(LintEdit {
                        start: token.span.start,
                        end: token.span.end,
                        replacement,
                    }),
                    None,
                ),
                Err(reason) => (None, Some(reason)),
            };
            Some(LintDiagnostic {
                code: LONG_LITERAL.code,
                message: LONG_LITERAL.message,
                remediation: LONG_LITERAL.remediation,
                start: token.span.start,
                end: token.span.end,
                fix,
                fix_unavailable_reason: reason,
            })
        })
        .collect()
}

fn is_string(kind: TokenType) -> bool {
    matches!(
        kind,
        TokenType::String
            | TokenType::DollarString
            | TokenType::EscapeString
            | TokenType::RawString
            | TokenType::NationalString
            | TokenType::UnicodeString
            | TokenType::ByteString
            | TokenType::TripleSingleQuotedString
            | TokenType::TripleDoubleQuotedString
            | TokenType::HeredocString
            | TokenType::HeredocStringAlternative
    )
}

fn replacement(
    source: &str,
    token: &Token,
    index: usize,
    context: &LiteralContext<'_>,
) -> Result<String, &'static str> {
    let LiteralContext {
        tokens,
        dialect,
        limit,
        header,
        ..
    } = *context;
    if header {
        return Err("MODEL and declaration header strings require a constant token");
    }
    if token.token_type != TokenType::String || !source.starts_with('\'') || !source.ends_with('\'')
    {
        return Err(
            "Dollar-quoted, raw, escape, prefixed and multiline strings cannot be safely split",
        );
    }
    let value = &source[1..source.len() - 1];
    if value.contains('\\') || value.contains("''") {
        return Err("Splitting literals containing escape sequences or doubled quotes is refused");
    }
    let previous = tokens[..index]
        .iter()
        .rev()
        .find(|token| !is_layout(token) && !is_comment(token));
    if previous.is_some_and(|token| {
        matches!(
            token.text.to_ascii_uppercase().as_str(),
            "DATE" | "TIME" | "TIMESTAMP" | "TIMESTAMPTZ" | "INTERVAL" | "DATETIME"
        )
    }) {
        return Err("Typed literals require a constant token");
    }
    let first = tokens
        .iter()
        .find(|token| !is_layout(token) && !is_comment(token));
    if first.is_none_or(|token| {
        !matches!(
            token.token_type,
            TokenType::Select | TokenType::With | TokenType::LParen | TokenType::Values
        )
    }) || previous.is_some_and(|token| {
        matches!(
            token.text.to_ascii_uppercase().as_str(),
            "AS" | "COLLATE" | "ESCAPE"
        )
    }) {
        return Err("This SQL position requires a constant token");
    }
    let pieces = split(value, limit).ok_or(
        "No safe space, comma or top-level regex alternation boundary fits max_literal_length",
    )?;
    let quoted: Vec<String> = pieces.iter().map(|piece| format!("'{piece}'")).collect();
    let concatenation = match dialect {
        DialectType::MySQL => Ok(format!("CONCAT({})", quoted.join(", "))),
        DialectType::TSQL if value.is_ascii() && value.len() <= MAX_TSQL_LITERAL_BYTES => {
            Ok(format!("({})", quoted.join(" + ")))
        }
        DialectType::TSQL => {
            Err("T-SQL concatenation could truncate this value or change its encoding")
        }
        DialectType::Generic
        | DialectType::DuckDB
        | DialectType::Snowflake
        | DialectType::PostgreSQL
        | DialectType::Redshift
        | DialectType::BigQuery
        | DialectType::SQLite
        | DialectType::Trino
        | DialectType::Presto
        | DialectType::Spark
        | DialectType::Databricks
        | DialectType::Oracle => Ok(format!("({})", quoted.join(" || "))),
        _ => Err("No proven safe string concatenation form is available for this dialect"),
    }?;
    Ok(format!("COALESCE({concatenation}, '')"))
}

fn split(value: &str, limit: usize) -> Option<Vec<String>> {
    let chars: Vec<char> = value.chars().collect();
    let mut depth: usize = 0;
    let mut bracket: bool = false;
    let mut pipes: Vec<(usize, usize)> = Vec::new();
    for (index, character) in chars.iter().enumerate() {
        match character {
            '[' => bracket = true,
            ']' => bracket = false,
            '(' if !bracket => depth += 1,
            ')' if !bracket => depth = depth.saturating_sub(1),
            '|' if !bracket => pipes.push((index + 1, depth)),
            _ => (),
        }
    }
    let outer_depth = pipes.iter().map(|(_, depth)| *depth).min();
    let mut boundaries: Vec<usize> = if let Some(outer_depth) = outer_depth {
        pipes
            .into_iter()
            .filter(|(_, depth)| *depth == outer_depth)
            .map(|(index, _)| index)
            .collect()
    } else {
        chars
            .iter()
            .enumerate()
            .filter(|(_, character)| matches!(character, ' ' | ','))
            .map(|(index, _)| index + 1)
            .collect()
    };
    if outer_depth.is_some() {
        if value.starts_with("^(") {
            boundaries.push(2);
        }
        if value.ends_with(")$") {
            boundaries.push(chars.len() - 2);
        }
    }
    let mut start: usize = 0;
    let mut pieces: Vec<String> = Vec::new();
    while chars.len() - start > limit {
        let end = boundaries
            .iter()
            .copied()
            .filter(|end| *end > start && *end - start <= limit)
            .max()?;
        pieces.push(chars[start..end].iter().collect());
        start = end;
    }
    pieces.push(chars[start..].iter().collect());
    Some(pieces)
}
