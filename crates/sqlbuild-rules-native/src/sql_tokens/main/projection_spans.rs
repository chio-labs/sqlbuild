//! Authored spans of the top-level items of one select list.

use polyglot_sql::tokens::{Token, TokenType};

use crate::sql_tokens::constants::PROJECTION_ENDS;

/// Spans of each top-level projection item of the select starting at token `select`.
pub(crate) fn projection_spans(tokens: &[Token], select: usize) -> Vec<(usize, usize)> {
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut depth: usize = 0;
    let mut start: Option<usize> = None;
    let mut end: usize = 0;
    for token in tokens.iter().skip(select + 1) {
        if matches!(
            token.token_type,
            TokenType::Space | TokenType::Break | TokenType::LineComment | TokenType::BlockComment
        ) {
            continue;
        }
        match token.token_type {
            TokenType::LParen => depth += 1,
            TokenType::RParen if depth == 0 => break,
            TokenType::RParen => depth -= 1,
            TokenType::Comma if depth == 0 => {
                if let Some(first) = start.take() {
                    spans.push((first, end));
                }
                continue;
            }
            kind if depth == 0 && PROJECTION_ENDS.contains(&kind) => break,
            TokenType::Distinct | TokenType::All if depth == 0 && start.is_none() => continue,
            _ => {}
        }
        start.get_or_insert(token.span.start);
        end = token.span.end;
    }
    if let Some(first) = start {
        spans.push((first, end));
    }
    spans
}
