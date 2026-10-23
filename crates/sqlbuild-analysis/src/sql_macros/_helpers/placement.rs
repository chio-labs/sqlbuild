//! Where a call stands in its caller: its query part, separators and the caller's names.

use crate::sql_macros::_helpers::header::unquoted;
use crate::sql_macros::_helpers::lexing::{Token, TokenKind, closing_token};
use crate::sql_macros::constants::{AS_KEYWORD, AT_SIGN, COMMA, SELECT_KEYWORD, WITH_KEYWORD};
use crate::sql_macros::models::{CallPosition, CallScope};

/// Tokens before the `(` of `DISTINCT ON (...)`.
const DISTINCT_ON_TOKENS: usize = 2;
/// Keywords that open a query inside a parenthesis.
const QUERY_OPENERS: [&str; 4] = ["SELECT", "WITH", "VALUES", "FROM"];
/// Keywords that combine the selects of a query.
const SET_OPERATIONS: [&str; 3] = ["UNION", "INTERSECT", "EXCEPT"];
/// A star, which an `EXCEPT` column list may follow as a modifier, not a set operation.
const STAR: &str = "*";
/// The words that may stand between a set operation and its parenthesised right branch.
const SET_OPERATION_MODIFIERS: [&str; 3] = ["ALL", "DISTINCT", "NAME"];
/// Tokens from `@` to a macro call's name: `@`, the kind, `.` and the name.
const CALL_PREFIX_TOKENS: usize = 4;
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
const EXPRESSION_OPERATOR_WORDS: [&str; 16] = [
    "AND", "OR", "IS", "IN", "NOT", "LIKE", "ILIKE", "BETWEEN", "COLLATE", "SIMILAR", "GLOB",
    "REGEXP", "AT", "OVER", "FILTER", "WITHIN",
];
/// Words before a call that leave it inside an expression rather than after a select-list item.
const ITEM_CONTINUING_WORDS: [&str; 14] = [
    "AS", "CASE", "WHEN", "THEN", "ELSE", "AND", "OR", "NOT", "IS", "IN", "LIKE", "BETWEEN",
    "INTERVAL", "ON",
];

/// A caller's tokens and where one call stands among them.
pub(crate) struct CallSite<'a> {
    pub(crate) sql: &'a str,
    pub(crate) tokens: &'a [Token],
    /// Index of the last token before the call, if any.
    pub(crate) previous: Option<usize>,
    /// Index of the first token after the call, if any.
    pub(crate) next: Option<usize>,
    /// Index of the first token after the call and any list comma right after it, if any.
    pub(crate) after_replaced: Option<usize>,
}

impl<'a> CallSite<'a> {
    /// The call spanning bytes `start..end` of `sql`, replacing it up to `replaced_end`.
    pub(crate) fn new(
        sql: &'a str,
        tokens: &'a [Token],
        (start, end): (usize, usize),
        replaced_end: usize,
    ) -> Self {
        let previous: Option<usize> = tokens.iter().rposition(|token| token.end <= start);
        let next: Option<usize> = tokens.iter().position(|token| token.start >= end);
        let after_replaced: Option<usize> =
            tokens.iter().position(|token| token.start >= replaced_end);
        Self {
            sql,
            tokens,
            previous,
            next,
            after_replaced,
        }
    }

    /// Whether the expansion replaces the comma right after the call.
    fn absorbs_comma(&self) -> bool {
        self.next != self.after_replaced
    }

    /// Where a list call's replaced text ends: after a comma right after it, else at its end.
    pub(crate) fn list_replaced_end(&self, end: usize) -> usize {
        let in_list: bool = matches!(
            self.position(),
            CallPosition::CteList | CallPosition::SelectList
        );
        match self.next_token() {
            Some(comma) if in_list && comma.is(self.sql, COMMA) => comma.end,
            _ => end,
        }
    }

    /// Whether token `index` is the `)` closing a `@sql.name(...)` or `@py.name(...)` call.
    fn closes_macro_call(&self, index: usize) -> bool {
        self.opening(index).is_some_and(|open| {
            open >= CALL_PREFIX_TOKENS
                && self.tokens[open - 1].kind == TokenKind::Word
                && self.tokens[open - 2].is(self.sql, ".")
                && self.tokens[open - CALL_PREFIX_TOKENS].is(self.sql, AT_SIGN)
        })
    }

    /// Whether token `index` is the `)` closing `DISTINCT ON (...)`.
    fn closes_distinct_on(&self, index: usize) -> bool {
        self.opening(index).is_some_and(|open| {
            open >= DISTINCT_ON_TOKENS
                && self.tokens[open - 1].is_word(self.sql, "ON")
                && self.tokens[open - DISTINCT_ON_TOKENS].is_word(self.sql, "DISTINCT")
        })
    }

    /// The index of the bracket token `index` closes, if it closes one.
    fn opening(&self, index: usize) -> Option<usize> {
        let mut depth: usize = 0;
        for open in (0..=index).rev() {
            let token: &Token = &self.tokens[open];
            if token.kind != TokenKind::Punct {
                continue;
            }
            match token.text(self.sql) {
                ")" | "]" | "}" => depth += 1,
                "(" | "[" | "{" => {
                    depth = depth.saturating_sub(1);
                    if depth == 0 {
                        return Some(open);
                    }
                }
                _ => {}
            }
        }
        None
    }

    /// Whether the token before the call ends a select-list item, such as `o.id` or `SUM(x)`.
    fn follows_item(&self) -> bool {
        let Some(token) = self.previous_token() else {
            return false;
        };
        match token.kind {
            TokenKind::Quoted | TokenKind::Number | TokenKind::Text => true,
            TokenKind::Punct => {
                let closing: bool = token.is(self.sql, ")") || token.is(self.sql, "]");
                closing
                    && self
                        .previous
                        .is_some_and(|index| !self.closes_distinct_on(index))
            }
            TokenKind::Word => {
                let upper: String = token.text(self.sql).to_ascii_uppercase();
                !ITEM_CONTINUING_WORDS.contains(&upper.as_str())
                    && !CLAUSE_KEYWORDS.contains(&upper.as_str())
                    && !matches!(upper.as_str(), "DISTINCT" | "ALL")
            }
            TokenKind::Operator => false,
        }
    }

    /// Whether the column-list call is followed by an `AS` alias, as in `@sql.m(o) AS x`.
    pub(crate) fn has_alias(&self) -> bool {
        !self.absorbs_comma()
            && self
                .next_token()
                .is_some_and(|next| next.is_word(self.sql, "AS"))
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
            (Some((_, clause)), Some(_))
                if clause == SELECT_KEYWORD && self.follows_item() && self.ends_select_item() =>
            {
                CallPosition::SelectList
            }
            _ => CallPosition::Expression,
        }
    }

    /// The alias of the select-list item the call is the whole of, as `@sql.m(x) AS name`.
    pub(crate) fn whole_item_alias(&self) -> Option<String> {
        let opens_item: bool = self.previous_token().is_some_and(|token| {
            matches!(
                token.text(self.sql).to_ascii_uppercase().as_str(),
                "SELECT" | "DISTINCT" | "ALL" | ","
            )
        });
        if !opens_item || self.position() != CallPosition::SelectList {
            return None;
        }
        let next: usize = self.next?;
        let alias_index: usize = if self.tokens[next].is_word(self.sql, AS_KEYWORD) {
            next + 1
        } else {
            next
        };
        let alias: &Token = self.tokens.get(alias_index)?;
        let alias_text: String = alias.text(self.sql).to_ascii_uppercase();
        let named: bool = match alias.kind {
            TokenKind::Quoted => true,
            TokenKind::Word => {
                !SELECT_LIST_ENDS.contains(&alias_text.as_str())
                    && !EXPRESSION_OPERATOR_WORDS.contains(&alias_text.as_str())
                    && alias_text != AS_KEYWORD
            }
            _ => false,
        };
        if !named {
            return None;
        }
        let ends_item: bool = match self.tokens.get(alias_index + 1) {
            None => true,
            Some(after) => {
                let text: String = after.text(self.sql).to_ascii_uppercase();
                matches!(text.as_str(), "," | ")" | ";")
                    || (after.kind == TokenKind::Word && SELECT_LIST_ENDS.contains(&text.as_str()))
            }
        };
        ends_item.then(|| unquoted(alias.text(self.sql)))
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

    /// The separators around inserted CTEs, which replace the comma right after the call.
    pub(crate) fn cte_separators(&self) -> (&'static str, &'static str) {
        let before: &'static str = match self.previous {
            Some(index)
                if self.tokens[index].is(self.sql, ")") && !self.closes_macro_call(index) =>
            {
                ", "
            }
            _ => "",
        };
        let after: &'static str = match self.after_replaced {
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
        let before: &'static str = match self.previous {
            Some(index) if self.follows_item() && !self.closes_macro_call(index) => ", ",
            _ => "",
        };
        let after: &'static str = match self.after_replaced.map(|index| &self.tokens[index]) {
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
        (before, after)
    }

    /// The comma an expression expansion writes back for the one it replaces, if any.
    pub(crate) fn expression_separator(&self) -> &'static str {
        if self.absorbs_comma() { "," } else { "" }
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

/// One top-level CTE: its name, the byte span of its whole definition and of its body.
pub(crate) struct CtePart {
    pub(crate) name: String,
    pub(crate) definition: (usize, usize),
    pub(crate) body: (usize, usize),
}

/// The top-level CTEs of a query, where its `WITH` list ends and its final query starts.
pub(crate) struct QueryParts {
    pub(crate) ctes: Vec<CtePart>,
    /// Byte span of the `WITH` list, from `WITH` to the end of its last item.
    pub(crate) with_list: Option<(usize, usize)>,
    /// Byte offset of the query after the `WITH` list.
    pub(crate) main: usize,
}

impl QueryParts {
    /// The part holding byte `offset`.
    pub(crate) fn scope_of(&self, offset: usize) -> CallScope {
        if let Some(cte) = self
            .ctes
            .iter()
            .find(|cte| cte.body.0 <= offset && offset < cte.body.1)
        {
            return CallScope::Cte(cte.name.clone());
        }
        match self.with_list {
            Some((start, _)) if start <= offset && offset < self.main => CallScope::WithList,
            _ => CallScope::Main,
        }
    }

    /// Whether byte `offset` stands outside subqueries in a scope without set operations.
    pub(crate) fn plain_select(&self, text: &str, scanned: &[Token], offset: usize) -> bool {
        let range: (usize, usize) = match self.scope_of(offset) {
            CallScope::WithList => return true,
            CallScope::Cte(name) => match self.ctes.iter().find(|cte| cte.name == name) {
                Some(cte) => cte.body,
                None => return false,
            },
            CallScope::Main => (self.main, text.len()),
        };
        let mut queries: Vec<bool> = Vec::new();
        let mut nested_at_call: Option<bool> = None;
        let inside = scanned
            .iter()
            .enumerate()
            .filter(|(_, token)| range.0 <= token.start && token.end <= range.1);
        for (index, token) in inside {
            if nested_at_call.is_none() && token.start >= offset {
                nested_at_call = Some(queries.iter().any(|query| *query));
            }
            if token.kind == TokenKind::Punct {
                match token.text(text) {
                    "(" | "[" | "{" => queries.push(
                        scanned
                            .get(index + 1)
                            .is_some_and(|next| opens_query(text, next)),
                    ),
                    ")" | "]" | "}" => {
                        let _ = queries.pop();
                    }
                    _ => {}
                }
                continue;
            }
            let at_top: bool = queries.is_empty();
            if at_top && token.kind == TokenKind::Word && is_set_operation(token.text(text)) {
                return false;
            }
        }
        nested_at_call == Some(false)
    }
}

impl QueryParts {
    /// The set-operation branch byte `offset` stands in; `None` where it cannot be counted.
    pub(crate) fn branch_of(&self, text: &str, scanned: &[Token], offset: usize) -> Option<usize> {
        let range: (usize, usize) = match self.scope_of(offset) {
            CallScope::WithList => return None,
            CallScope::Cte(name) => self.ctes.iter().find(|cte| cte.name == name)?.body,
            CallScope::Main => (self.main, text.len()),
        };
        let inside: Vec<(usize, &Token)> = scanned
            .iter()
            .enumerate()
            .filter(|(_, token)| range.0 <= token.start && token.end <= range.1)
            .collect();
        if inside
            .first()
            .is_some_and(|(_, token)| token.is_word(text, WITH_KEYWORD))
        {
            return None;
        }
        let mut depth: usize = 0;
        let mut branch: usize = 0;
        let mut at_call: Option<usize> = None;
        let mut previous_at_top: Option<&Token> = None;
        for (index, token) in inside {
            if at_call.is_none() && token.start >= offset {
                if depth != 0 {
                    return None;
                }
                at_call = Some(branch);
            }
            if token.kind == TokenKind::Punct {
                match token.text(text) {
                    "(" | "[" | "{" => {
                        let query: bool = scanned
                            .get(index + 1)
                            .is_some_and(|next| opens_query(text, next));
                        let branch_start: bool = previous_at_top.is_none_or(|previous| {
                            let word: &str = previous.text(text);
                            is_set_operation(word)
                                || SET_OPERATION_MODIFIERS
                                    .iter()
                                    .any(|modifier| word.eq_ignore_ascii_case(modifier))
                        });
                        if depth == 0 && query && branch_start {
                            return None;
                        }
                        depth += 1;
                    }
                    ")" | "]" | "}" => depth = depth.saturating_sub(1),
                    _ => {}
                }
            }
            if depth == 0 {
                let star_modifier: bool =
                    previous_at_top.is_some_and(|previous| previous.text(text) == STAR);
                if token.kind == TokenKind::Word
                    && is_set_operation(token.text(text))
                    && !star_modifier
                {
                    branch += 1;
                }
                previous_at_top = Some(token);
            }
        }
        at_call
    }
}

/// Whether `token` opens a query, as the first token inside a parenthesis.
fn opens_query(text: &str, token: &Token) -> bool {
    QUERY_OPENERS
        .iter()
        .any(|keyword| token.is_word(text, keyword))
}

/// Whether `word` is `UNION`, `INTERSECT` or `EXCEPT`.
fn is_set_operation(word: &str) -> bool {
    SET_OPERATIONS
        .iter()
        .any(|keyword| word.eq_ignore_ascii_case(keyword))
}

/// The top-level parts of `text`, or `None` if its `WITH` list cannot be read.
pub(crate) fn top_level_parts(text: &str, scanned: &[Token]) -> Option<QueryParts> {
    let Some(first) = scanned.first() else {
        return Some(QueryParts {
            ctes: Vec::new(),
            with_list: None,
            main: 0,
        });
    };
    if !first.is_word(text, "WITH") {
        return Some(QueryParts {
            ctes: Vec::new(),
            with_list: None,
            main: first.start,
        });
    }
    let mut ctes: Vec<CtePart> = Vec::new();
    let mut index: usize = 1;
    if scanned
        .get(index)
        .is_some_and(|token| token.is_word(text, "RECURSIVE"))
    {
        index += 1;
    }
    loop {
        let token: &Token = scanned.get(index)?;
        if token.is(text, ",") {
            index += 1;
            continue;
        }
        if token.is(text, "@") {
            let open: usize = index
                + scanned[index..]
                    .iter()
                    .position(|candidate| candidate.is(text, "("))?;
            index = closing_token(text, scanned, open)? + 1;
            continue;
        }
        if !matches!(token.kind, TokenKind::Word | TokenKind::Quoted) {
            return None;
        }
        let mut cursor: usize = index + 1;
        if scanned.get(cursor).is_some_and(|open| open.is(text, "(")) {
            cursor = closing_token(text, scanned, cursor)? + 1;
        }
        if !scanned
            .get(cursor)
            .is_some_and(|keyword| keyword.is_word(text, "AS"))
        {
            break;
        }
        cursor += 1;
        while scanned
            .get(cursor)
            .is_some_and(|word| word.is_word(text, "NOT") || word.is_word(text, "MATERIALIZED"))
        {
            cursor += 1;
        }
        if !scanned.get(cursor).is_some_and(|open| open.is(text, "(")) {
            return None;
        }
        let close: usize = closing_token(text, scanned, cursor)?;
        ctes.push(CtePart {
            name: unquoted(token.text(text)),
            definition: (token.start, scanned[close].end),
            body: (scanned[cursor].end, scanned[close].start),
        });
        index = close + 1;
    }
    let main: usize = scanned[index].start;
    Some(QueryParts {
        ctes,
        with_list: Some((first.start, main)),
        main,
    })
}
