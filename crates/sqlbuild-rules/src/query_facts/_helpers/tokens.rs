use crate::query_facts::constants::MIN_CAST_TOKENS;
use crate::query_facts::models::ComparisonSpan;
use polyglot_sql::tokens::{Token, TokenType};
use std::cell::RefCell;
use std::collections::HashSet;
use std::ops::Range;

const ITEM_CLAUSES: [&str; 14] = [
    "FROM",
    "WHERE",
    "GROUP",
    "HAVING",
    "QUALIFY",
    "ORDER",
    "LIMIT",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "MINUS",
    "WINDOW",
    "INTO",
    "FETCH",
];
const LEFT_BOUNDARIES: [&str; 18] = [
    "AND", "OR", "NOT", "WHERE", "ON", "WHEN", "THEN", "ELSE", "HAVING", "QUALIFY", "SELECT", "BY",
    "USING", "AS", "FROM", "JOIN", "DISTINCT", "RETURN",
];
const RIGHT_BOUNDARIES: [&str; 31] = [
    "AND",
    "OR",
    "THEN",
    "ELSE",
    "WHEN",
    "FROM",
    "WHERE",
    "GROUP",
    "ORDER",
    "HAVING",
    "QUALIFY",
    "LIMIT",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "MINUS",
    "AS",
    "JOIN",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "CROSS",
    "NATURAL",
    "ON",
    "USING",
    "WINDOW",
    "ASC",
    "DESC",
    "NULLS",
    "OFFSET",
];
const NON_FUNCTION_CALLS: [&str; 41] = [
    "IN",
    "CAST",
    "TRY_CAST",
    "SAFE_CAST",
    "EXISTS",
    "VALUES",
    "OVER",
    "FILTER",
    "WITHIN",
    "AS",
    "FROM",
    "JOIN",
    "ON",
    "USING",
    "AND",
    "OR",
    "NOT",
    "SELECT",
    "WHERE",
    "ANY",
    "ALL",
    "SOME",
    "INTERVAL",
    "EXTRACT",
    "SUBSTRING",
    "SUBSTR",
    "TRIM",
    "POSITION",
    "CEIL",
    "FLOOR",
    "OVERLAY",
    "CONVERT",
    "ARRAY",
    "STRUCT",
    "WHEN",
    "THEN",
    "ELSE",
    "CASE",
    "IS",
    "LIKE",
    "BETWEEN",
];
const PREFIX_KEYWORDS: [&str; 3] = ["NOT", "INTERVAL", "EXISTS"];
const PREFIX_CALLS: [&str; 12] = [
    "CAST",
    "TRY_CAST",
    "SAFE_CAST",
    "CEIL",
    "FLOOR",
    "SUBSTRING",
    "SUBSTR",
    "TRIM",
    "POSITION",
    "OVERLAY",
    "CONVERT",
    "TRY_CONVERT",
];
const TYPED_STRING_KEYWORDS: [&str; 7] = [
    "DATE",
    "TIME",
    "TIMESTAMP",
    "DATETIME",
    "TIMESTAMP_NTZ",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_TZ",
];

/// The comparison operator a comparison fact's source range is anchored on.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum ComparisonOperator {
    Eq,
    NotEq,
    Lt,
    LtEq,
    Gt,
    GtEq,
    Between,
    In,
}

/// One SELECT keyword's extent and its projection items as token ranges.
#[derive(Debug)]
pub(crate) struct SelectTokens {
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) items: Vec<Range<usize>>,
}

/// The code tokens of a normalized query, without comments, over its text.
pub(crate) struct QueryTokens<'a> {
    tokens: Vec<Token>,
    sql: &'a str,
    bytes: Vec<usize>,
    used: RefCell<HashSet<usize>>,
}

impl<'a> QueryTokens<'a> {
    pub(crate) fn new(tokens: Vec<Token>, sql: &'a str) -> Self {
        let mut bytes: Vec<usize> = sql.char_indices().map(|(byte, _)| byte).collect();
        bytes.push(sql.len());
        Self {
            sql,
            bytes,
            used: RefCell::default(),
            tokens: tokens
                .into_iter()
                .filter(|token| {
                    !matches!(
                        token.token_type,
                        TokenType::BlockComment
                            | TokenType::LineComment
                            | TokenType::Space
                            | TokenType::Break
                    )
                })
                .collect(),
        }
    }

    /// The normalized text between characters `start` and `end`.
    pub(crate) fn slice(&self, start: usize, end: usize) -> Option<&'a str> {
        self.sql.get(*self.bytes.get(start)?..*self.bytes.get(end)?)
    }

    pub(crate) fn start(&self, index: usize) -> usize {
        self.tokens[index].span.start
    }

    pub(crate) fn end(&self, index: usize) -> usize {
        self.tokens[index].span.end
    }

    fn kind(&self, index: usize) -> Option<TokenType> {
        self.tokens.get(index).map(|token| token.token_type)
    }

    fn word(&self, index: usize) -> Option<String> {
        let token = self.tokens.get(index)?;
        if literal(token.token_type) {
            return None;
        }
        token
            .text
            .split_whitespace()
            .next()
            .map(str::to_ascii_uppercase)
    }

    fn is_word(&self, index: usize, words: &[&str]) -> bool {
        self.word(index)
            .is_some_and(|word| words.contains(&word.as_str()))
    }

    fn opens(&self, index: usize) -> bool {
        matches!(
            self.kind(index),
            Some(TokenType::LParen | TokenType::LBracket | TokenType::LBrace)
        )
    }

    fn closes(&self, index: usize) -> bool {
        matches!(
            self.kind(index),
            Some(TokenType::RParen | TokenType::RBracket | TokenType::RBrace)
        )
    }

    fn matching_close(&self, open: usize) -> Option<usize> {
        let mut depth = 0_usize;
        for index in open..self.tokens.len() {
            if self.opens(index) {
                depth += 1;
            } else if self.closes(index) {
                depth = depth.checked_sub(1)?;
                if depth == 0 {
                    return Some(index);
                }
            }
        }
        None
    }

    pub(crate) fn len(&self) -> usize {
        self.tokens.len()
    }

    /// The first token at parenthesis depth 0 spelling `word`.
    pub(crate) fn top_level_word(&self, word: &str) -> Option<usize> {
        let mut depth = 0_usize;
        for index in 0..self.tokens.len() {
            if self.opens(index) {
                depth += 1;
            } else if self.closes(index) {
                depth = depth.saturating_sub(1);
            } else if depth == 0 && self.is_word(index, &[word]) {
                return Some(index);
            }
        }
        None
    }

    /// Whether a function call starts in `range`.
    pub(crate) fn calls_function(&self, range: Range<usize>) -> bool {
        range.into_iter().any(|index| {
            self.opens(index + 1)
                && self.kind(index + 1) == Some(TokenType::LParen)
                && self.word(index).is_some_and(|word| {
                    word.starts_with(|first: char| first.is_ascii_alphabetic() || first == '_')
                        && !NON_FUNCTION_CALLS.contains(&word.as_str())
                })
        })
    }

    /// Every SELECT keyword's region and projection items, in source order.
    pub(crate) fn selects(&self) -> Vec<SelectTokens> {
        (0..self.tokens.len())
            .filter(|index| self.kind(*index) == Some(TokenType::Select))
            .map(|index| self.select_tokens(index))
            .collect()
    }

    fn select_tokens(&self, select: usize) -> SelectTokens {
        let mut end = self.tokens.len();
        let mut depth = 0_usize;
        for index in select + 1..self.tokens.len() {
            if self.opens(index) {
                depth += 1;
            } else if self.closes(index) {
                if depth == 0 {
                    end = index;
                    break;
                }
                depth -= 1;
            } else if depth == 0
                && (self.kind(index) == Some(TokenType::Semicolon)
                    || (self.is_word(index, &["UNION", "INTERSECT", "MINUS"]))
                    || (self.is_word(index, &["EXCEPT"])
                        && self.kind(index - 1) != Some(TokenType::Star)))
            {
                end = index;
                break;
            }
        }
        let mut cursor = select + 1;
        loop {
            if self.is_word(cursor, &["DISTINCT", "ALL"]) {
                cursor += 1;
                if self.is_word(cursor, &["ON"])
                    && self.opens(cursor + 1)
                    && let Some(close) = self.matching_close(cursor + 1)
                {
                    cursor = close + 1;
                }
            } else if self.is_word(cursor, &["TOP"]) {
                cursor += 2;
            } else {
                break;
            }
        }
        let mut items: Vec<Range<usize>> = Vec::new();
        let mut item_start = cursor;
        let mut depth = 0_usize;
        let mut index = cursor;
        while index < end {
            if self.opens(index) {
                depth += 1;
            } else if self.closes(index) {
                depth = depth.saturating_sub(1);
            } else if depth == 0 {
                if self.kind(index) == Some(TokenType::Comma) {
                    items.push(item_start..index);
                    item_start = index + 1;
                } else if self.is_word(index, &ITEM_CLAUSES)
                    && !(self.is_word(index, &["EXCEPT"])
                        && self.kind(index - 1) == Some(TokenType::Star))
                {
                    break;
                }
            }
            index += 1;
        }
        if item_start < index {
            items.push(item_start..index);
        }
        SelectTokens {
            start: self.start(select),
            end: if end < self.tokens.len() {
                self.start(end)
            } else {
                usize::MAX
            },
            items,
        }
    }

    /// The item's tokens without a trailing alias.
    pub(crate) fn expression_range(&self, item: &Range<usize>, aliased: bool) -> Range<usize> {
        let mut end = item.end;
        if aliased && end > item.start {
            end -= 1;
            if end > item.start && self.is_word(end - 1, &["AS"]) {
                end -= 1;
            }
        }
        item.start..end
    }

    /// The first `*` of an item.
    pub(crate) fn star_start(&self, item: &Range<usize>) -> Option<usize> {
        item.clone()
            .find(|index| self.kind(*index) == Some(TokenType::Star))
            .map(|index| self.start(index))
    }

    /// Where the expression starts: its first token past casts, prefix operators and parentheses.
    pub(crate) fn leaf_start(&self, range: &Range<usize>) -> Option<usize> {
        let mut index = range.start;
        while index < range.end {
            let next_opens = self.opens(index + 1);
            if matches!(
                self.kind(index),
                Some(
                    TokenType::LParen
                        | TokenType::LBracket
                        | TokenType::Dash
                        | TokenType::Plus
                        | TokenType::Tilde
                )
            ) || self.is_word(index, &PREFIX_KEYWORDS)
                || (self.is_word(index, &PREFIX_CALLS) && next_opens)
                || (self.is_word(index, &["ARRAY"])
                    && self.kind(index + 1) == Some(TokenType::LBracket))
                || (self.is_word(index, &TYPED_STRING_KEYWORDS)
                    && self.kind(index + 1) == Some(TokenType::String))
            {
                index += 1;
                continue;
            }
            if self.is_word(index, &["EXTRACT"]) && next_opens {
                let close = self.matching_close(index + 1).unwrap_or(range.end);
                index = (index + 2..close)
                    .find(|candidate| self.is_word(*candidate, &["FROM"]))
                    .map_or(index + 2, |from| from + 1);
                continue;
            }
            return Some(self.start(index));
        }
        None
    }

    /// The source spelling of an outer `CAST(... AS type)` or `...::type` in `range`.
    pub(crate) fn cast_type(&self, range: &Range<usize>) -> Option<String> {
        let mut range = range.clone();
        while range.len() >= MIN_CAST_TOKENS
            && self.opens(range.start)
            && self.matching_close(range.start) == Some(range.end - 1)
        {
            range = range.start + 1..range.end - 1;
        }
        if range.len() < MIN_CAST_TOKENS {
            return None;
        }
        let (first, last) = if self.is_word(range.start, &PREFIX_CALLS[..3])
            && self.opens(range.start + 1)
            && self.matching_close(range.start + 1) == Some(range.end - 1)
        {
            let mut depth = 0_usize;
            let mut keyword = None;
            for index in range.start + 1..range.end - 1 {
                if self.opens(index) {
                    depth += 1;
                } else if self.closes(index) {
                    depth = depth.saturating_sub(1);
                } else if depth == 1 && self.is_word(index, &["AS"]) {
                    keyword = Some(index);
                }
            }
            (keyword? + 1, range.end - 2)
        } else {
            let mut depth = 0_usize;
            let mut colon = None;
            for index in range.clone() {
                if self.opens(index) {
                    depth += 1;
                } else if self.closes(index) {
                    depth = depth.saturating_sub(1);
                } else if depth == 0 && self.kind(index) == Some(TokenType::DColon) {
                    colon = Some(index);
                }
            }
            (colon? + 1, range.end - 1)
        };
        if first > last {
            return None;
        }
        self.slice(self.start(first), self.end(last))
            .map(str::to_owned)
    }

    fn operator(&self, index: usize, operator: ComparisonOperator) -> bool {
        match operator {
            ComparisonOperator::Eq => self.kind(index) == Some(TokenType::Eq),
            ComparisonOperator::NotEq => self.kind(index) == Some(TokenType::Neq),
            ComparisonOperator::Lt => self.kind(index) == Some(TokenType::Lt),
            ComparisonOperator::LtEq => self.kind(index) == Some(TokenType::Lte),
            ComparisonOperator::Gt => self.kind(index) == Some(TokenType::Gt),
            ComparisonOperator::GtEq => self.kind(index) == Some(TokenType::Gte),
            ComparisonOperator::Between => self.is_word(index, &["BETWEEN"]),
            ComparisonOperator::In => self.is_word(index, &["IN"]),
        }
    }

    /// The source range and start of a comparison, anchored on its operator token.
    pub(crate) fn comparison_range(
        &self,
        operator: ComparisonOperator,
        (left_end, right_start): (Option<usize>, Option<usize>),
        negated: bool,
        generated: &str,
    ) -> Option<ComparisonSpan> {
        let anchor = match (left_end, right_start) {
            (Some(end), _) => (0..self.tokens.len()).find(|index| {
                self.start(*index) >= end
                    && self.operator(*index, operator)
                    && !self.used.borrow().contains(index)
            }),
            (None, Some(start)) => (0..self.tokens.len()).rev().find(|index| {
                self.end(*index) <= start
                    && self.operator(*index, operator)
                    && !self.used.borrow().contains(index)
            }),
            (None, None) => {
                let wanted = compact(generated);
                (0..self.tokens.len()).find(|index| {
                    self.operator(*index, operator) && !self.used.borrow().contains(index) && {
                        let (first, last) = self.extent(*index, operator, negated);
                        self.slice(self.start(first), self.end(last))
                            .is_some_and(|text| compact(text) == wanted)
                    }
                })
            }
        }?;
        self.used.borrow_mut().insert(anchor);
        let (first, last) = self.extent(anchor, operator, negated);
        Some(ComparisonSpan {
            start: self.start(first),
            end: self.end(last),
            position: self.leaf_start(&(first..last + 1)),
        })
    }

    fn extent(&self, anchor: usize, operator: ComparisonOperator, negated: bool) -> (usize, usize) {
        let mut first = anchor;
        if negated && first > 0 && self.is_word(first - 1, &["NOT"]) {
            first -= 1;
        }
        let mut depth = 0_usize;
        while first > 0 {
            let index = first - 1;
            if self.closes(index) || self.is_word(index, &["END"]) {
                depth += 1;
            } else if self.opens(index) || self.is_word(index, &["CASE"]) {
                if depth == 0 {
                    break;
                }
                depth -= 1;
            } else if depth == 0
                && (matches!(
                    self.kind(index),
                    Some(TokenType::Comma | TokenType::Semicolon)
                ) || self.is_word(index, &LEFT_BOUNDARIES))
            {
                break;
            }
            first = index;
        }
        let mut last = anchor;
        let mut between = operator == ComparisonOperator::Between;
        let mut depth = 0_usize;
        let mut index = anchor + 1;
        while index < self.tokens.len() {
            if self.opens(index) || self.is_word(index, &["CASE"]) {
                depth += 1;
            } else if self.closes(index) || self.is_word(index, &["END"]) {
                if depth == 0 {
                    break;
                }
                depth -= 1;
            } else if depth == 0 {
                if matches!(
                    self.kind(index),
                    Some(TokenType::Comma | TokenType::Semicolon)
                ) {
                    break;
                }
                if between && self.is_word(index, &["AND"]) {
                    between = false;
                } else if self.is_word(index, &RIGHT_BOUNDARIES) {
                    break;
                }
            }
            last = index;
            index += 1;
        }
        (first, last)
    }
}

fn compact(text: &str) -> String {
    text.chars()
        .filter(|character| !character.is_whitespace())
        .flat_map(char::to_lowercase)
        .collect()
}

fn literal(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::String
            | TokenType::DollarString
            | TokenType::TripleDoubleQuotedString
            | TokenType::TripleSingleQuotedString
            | TokenType::Number
            | TokenType::QuotedIdentifier
            | TokenType::BitString
            | TokenType::HexString
            | TokenType::HexNumber
            | TokenType::ByteString
            | TokenType::NationalString
            | TokenType::EscapeString
            | TokenType::RawString
            | TokenType::HeredocString
            | TokenType::HeredocStringAlternative
            | TokenType::UnicodeString
    )
}
