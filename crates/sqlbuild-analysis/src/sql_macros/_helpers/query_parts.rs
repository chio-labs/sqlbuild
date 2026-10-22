//! A query's top-level parts: the CTEs of its `WITH` list and the query after them.

use crate::sql_macros::_helpers::header::unquoted;
use crate::sql_macros::_helpers::lexing::{Token, TokenKind, closing_token};
use crate::sql_macros::models::CallScope;

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
