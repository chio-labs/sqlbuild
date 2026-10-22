//! Where a call stands in its caller, the separators its expansion needs and the caller's names.

use crate::sql_macros::_helpers::lexing::{Token, TokenKind, closing_token};
use crate::sql_macros::constants::{AT_SIGN, COMMA, SELECT_KEYWORD, WITH_KEYWORD};
use crate::sql_macros::models::CallPosition;

/// Keywords that open the clause a call stands in, read backwards from the call.
const CLAUSE_KEYWORDS: [&str; 22] = [
    "WITH",
    "SELECT",
    "FROM",
    "WHERE",
    "HAVING",
    "GROUP",
    "ORDER",
    "QUALIFY",
    "WINDOW",
    "LIMIT",
    "ON",
    "JOIN",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "VALUES",
    "SET",
    "RETURNING",
    "INTO",
    "USING",
    "PARTITION",
    "OFFSET",
];
/// Keywords that end a select list.
const SELECT_LIST_ENDS: [&str; 13] = [
    "FROM",
    "INTO",
    "WHERE",
    "GROUP",
    "HAVING",
    "QUALIFY",
    "WINDOW",
    "ORDER",
    "LIMIT",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "OFFSET",
];
/// Words after a call that keep an expression in place: aliases and clause keywords are fine.
const EXPRESSION_SAFE_BEFORE: [&str; 13] = [
    "SELECT", "DISTINCT", "ALL", "WHERE", "HAVING", "ON", "WHEN", "THEN", "ELSE", "BY", "QUALIFY",
    "RETURN", "AS",
];
/// Words after a call that bind tighter than a select-list item boundary.
const EXPRESSION_OPERATOR_WORDS: [&str; 12] = [
    "AND", "OR", "IS", "IN", "NOT", "LIKE", "ILIKE", "BETWEEN", "COLLATE", "SIMILAR", "GLOB",
    "REGEXP",
];

/// A caller's tokens and where one call stands among them.
pub(crate) struct CallSite<'a> {
    pub(crate) sql: &'a str,
    pub(crate) tokens: &'a [Token],
    /// Index of the last token before the call, if any.
    pub(crate) previous: Option<usize>,
    /// Index of the first token after the call, if any.
    pub(crate) next: Option<usize>,
}

impl<'a> CallSite<'a> {
    /// The call spanning bytes `start..end` of `sql`.
    pub(crate) fn new(sql: &'a str, tokens: &'a [Token], start: usize, end: usize) -> Self {
        let previous: Option<usize> = tokens.iter().rposition(|token| token.end <= start);
        let next: Option<usize> = tokens.iter().position(|token| token.start >= end);
        Self {
            sql,
            tokens,
            previous,
            next,
        }
    }

    fn previous_token(&self) -> Option<&Token> {
        self.previous.map(|index| &self.tokens[index])
    }

    fn next_token(&self) -> Option<&Token> {
        self.next.map(|index| &self.tokens[index])
    }

    /// The clause keyword the call stands in and its token index, read backwards.
    pub(crate) fn clause(&self) -> Option<(usize, String)> {
        let mut depth: usize = 0;
        let previous: usize = self.previous?;
        for index in (0..=previous).rev() {
            let token: &Token = &self.tokens[index];
            match (token.kind, token.text(self.sql)) {
                (TokenKind::Punct, ")" | "]" | "}") => depth += 1,
                (TokenKind::Punct, "(" | "[" | "{") => {
                    if depth == 0 {
                        return None;
                    }
                    depth -= 1;
                }
                (TokenKind::Word, word) if depth == 0 => {
                    let upper: String = word.to_ascii_uppercase();
                    if CLAUSE_KEYWORDS.contains(&upper.as_str()) {
                        return Some((index, upper));
                    }
                }
                _ => {}
            }
        }
        None
    }

    /// Where the call stands: a CTE position, a select-list item position, or an expression.
    pub(crate) fn position(&self) -> CallPosition {
        let previous: Option<String> = self
            .previous_token()
            .map(|token| token.text(self.sql).to_ascii_uppercase());
        match (self.clause(), previous.as_deref()) {
            (Some((_, clause)), Some("WITH" | "RECURSIVE" | "," | ")"))
                if clause == WITH_KEYWORD =>
            {
                CallPosition::CteList
            }
            (Some((_, clause)), Some("SELECT" | "DISTINCT" | "ALL" | ","))
                if clause == SELECT_KEYWORD && self.ends_select_item() =>
            {
                CallPosition::SelectList
            }
            _ => CallPosition::Expression,
        }
    }

    /// Whether the token after the call ends a select-list item.
    fn ends_select_item(&self) -> bool {
        let Some(next) = self.next_token() else {
            return true;
        };
        let text: String = next.text(self.sql).to_ascii_uppercase();
        match next.kind {
            TokenKind::Punct => matches!(text.as_str(), "," | ")" | ";"),
            TokenKind::Word => !EXPRESSION_OPERATOR_WORDS.contains(&text.as_str()),
            TokenKind::Quoted | TokenKind::Number | TokenKind::Text => true,
            TokenKind::Operator => text == AT_SIGN,
        }
    }

    /// The separators a CTE list needs around the inserted CTEs.
    pub(crate) fn cte_separators(&self) -> (&'static str, &'static str) {
        let before: &'static str = match self.previous_token() {
            Some(token) if token.is(self.sql, ")") => ", ",
            _ => "",
        };
        let after: &'static str = match self.next {
            Some(index) if self.starts_cte(index) => ",",
            _ => "",
        };
        (before, after)
    }

    /// Whether a CTE definition or another macro call starts at token `index`.
    fn starts_cte(&self, index: usize) -> bool {
        let token: &Token = &self.tokens[index];
        if token.is(self.sql, "@") {
            return true;
        }
        if !matches!(token.kind, TokenKind::Word | TokenKind::Quoted) {
            return false;
        }
        match self.tokens.get(index + 1) {
            Some(after) if after.is_word(self.sql, "AS") => true,
            Some(after) if after.is(self.sql, "(") => {
                closing_token(self.sql, self.tokens, index + 1)
                    .and_then(|close| self.tokens.get(close + 1))
                    .is_some_and(|after| after.is_word(self.sql, "AS"))
            }
            _ => false,
        }
    }

    /// The separators a select list needs around the inserted columns.
    pub(crate) fn column_separators(&self) -> (&'static str, &'static str) {
        let after: &'static str = match self.next_token() {
            None => "",
            Some(next) => {
                let text: String = next.text(self.sql).to_ascii_uppercase();
                if matches!(text.as_str(), "," | ")" | ";")
                    || SELECT_LIST_ENDS.contains(&text.as_str())
                {
                    ""
                } else {
                    ","
                }
            }
        };
        ("", after)
    }

    /// Whether an expression expansion needs parentheses where the call stands.
    pub(crate) fn expression_needs_parentheses(&self) -> bool {
        let safe_before: bool = match self.previous_token() {
            None => true,
            Some(token) => {
                let text: String = token.text(self.sql).to_ascii_uppercase();
                matches!(text.as_str(), "," | "(" | "[")
                    || (token.kind == TokenKind::Word
                        && EXPRESSION_SAFE_BEFORE.contains(&text.as_str()))
            }
        };
        let safe_after: bool = match self.next_token() {
            None => true,
            Some(token) => {
                let text: String = token.text(self.sql).to_ascii_uppercase();
                match token.kind {
                    TokenKind::Punct => matches!(text.as_str(), "," | ")" | "]" | ";"),
                    TokenKind::Word => !EXPRESSION_OPERATOR_WORDS.contains(&text.as_str()),
                    TokenKind::Quoted => true,
                    _ => false,
                }
            }
        };
        !(safe_before && safe_after)
    }
}

/// The names of the CTEs defined in the `WITH` list whose keyword is token `with_index`.
pub(crate) fn cte_names(sql: &str, tokens: &[Token], with_index: usize) -> Vec<(String, usize)> {
    let mut names: Vec<(String, usize)> = Vec::new();
    let mut index: usize = with_index + 1;
    if tokens
        .get(index)
        .is_some_and(|token| token.is_word(sql, "RECURSIVE"))
    {
        index += 1;
    }
    while let Some(token) = tokens.get(index) {
        if token.is(sql, ",") {
            index += 1;
            continue;
        }
        if token.is(sql, "@") {
            match tokens
                .iter()
                .skip(index)
                .position(|candidate| candidate.is(sql, "("))
                .and_then(|offset| closing_token(sql, tokens, index + offset))
            {
                Some(close) => {
                    index = close + 1;
                    continue;
                }
                None => break,
            }
        }
        if !matches!(token.kind, TokenKind::Word | TokenKind::Quoted) {
            break;
        }
        let name: String = crate::sql_macros::_helpers::header::unquoted(token.text(sql));
        let mut cursor: usize = index + 1;
        if tokens.get(cursor).is_some_and(|after| after.is(sql, "(")) {
            match closing_token(sql, tokens, cursor) {
                Some(close) => cursor = close + 1,
                None => break,
            }
        }
        if !tokens
            .get(cursor)
            .is_some_and(|after| after.is_word(sql, "AS"))
        {
            break;
        }
        cursor += 1;
        while tokens
            .get(cursor)
            .is_some_and(|word| word.is_word(sql, "NOT") || word.is_word(sql, "MATERIALIZED"))
        {
            cursor += 1;
        }
        if !tokens.get(cursor).is_some_and(|open| open.is(sql, "(")) {
            break;
        }
        let Some(close) = closing_token(sql, tokens, cursor) else {
            break;
        };
        names.push((name, token.start));
        index = close + 1;
    }
    names
}

/// The output names of the select list whose `SELECT` is token `select_index`.
pub(crate) fn select_names(
    sql: &str,
    tokens: &[Token],
    select_index: usize,
) -> Vec<(String, usize)> {
    let mut names: Vec<(String, usize)> = Vec::new();
    let mut item: Vec<Token> = Vec::new();
    let mut depth: usize = 0;
    let mut index: usize = select_index + 1;
    while tokens
        .get(index)
        .is_some_and(|token| token.is_word(sql, "DISTINCT") || token.is_word(sql, "ALL"))
    {
        index += 1;
    }
    while let Some(token) = tokens.get(index) {
        let text: String = token.text(sql).to_ascii_uppercase();
        if depth == 0
            && (SELECT_LIST_ENDS.contains(&text.as_str()) && token.kind == TokenKind::Word
                || matches!(text.as_str(), ")" | ";"))
        {
            break;
        }
        match text.as_str() {
            "(" | "[" | "{" => depth += 1,
            ")" | "]" | "}" => depth = depth.saturating_sub(1),
            _ => {}
        }
        if depth == 0 && text == COMMA {
            names.extend(item_name(sql, &item));
            item.clear();
        } else {
            item.push(*token);
        }
        index += 1;
    }
    names.extend(item_name(sql, &item));
    names
}

fn item_name(sql: &str, item: &[Token]) -> Option<(String, usize)> {
    let first: &Token = item.first()?;
    if first.is(sql, "@") {
        return None;
    }
    let last: &Token = item.last()?;
    if !matches!(last.kind, TokenKind::Word | TokenKind::Quoted) || last.is_word(sql, "END") {
        return None;
    }
    let before: Option<&Token> = item.len().checked_sub(2).map(|index| &item[index]);
    let named: bool = match before {
        None => true,
        Some(token) => {
            token.is_word(sql, "AS")
                || token.is(sql, ".")
                || matches!(token.kind, TokenKind::Punct) && token.is(sql, ")")
                || matches!(
                    token.kind,
                    TokenKind::Word | TokenKind::Quoted | TokenKind::Number | TokenKind::Text
                ) && !EXPRESSION_OPERATOR_WORDS
                    .contains(&token.text(sql).to_ascii_uppercase().as_str())
        }
    };
    named.then(|| {
        (
            crate::sql_macros::_helpers::header::unquoted(last.text(sql)),
            last.start,
        )
    })
}
