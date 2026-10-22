//! The `@...` constructs of a SQL string: SQL and Python macro calls, declarations, bare calls.

use crate::sql_macros::_helpers::lexing::{Token, TokenKind, closing_token, tokens};
use crate::sql_macros::constants::SQL_KIND_WORD;
use crate::sql_macros::errors::LexError;

/// One `@` construct and its byte span.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum AtConstruct {
    /// `@sql.name(...)`: the span of the whole call and of its arguments.
    Sql {
        name: String,
        start: usize,
        end: usize,
        arguments: (usize, usize),
    },
    /// `@py.name(...)`.
    Python {
        name: String,
        start: usize,
        end: usize,
    },
    /// `@name(...)` without a kind.
    Bare { name: String, start: usize },
}

const DECLARATION_WORDS: [&str; 3] = ["const", "enum", "param"];

/// Every SQL macro call, Python macro call and bare call in `sql`, top-level and nested.
pub(crate) fn at_constructs(sql: &str) -> Result<Vec<AtConstruct>, LexError> {
    if !sql.contains('@') {
        return Ok(Vec::new());
    }
    let scanned: Vec<Token> = tokens(sql)?;
    let mut found: Vec<AtConstruct> = Vec::new();
    for (index, token) in scanned.iter().enumerate() {
        if !token.is(sql, "@") {
            continue;
        }
        let Some(word) = scanned
            .get(index + 1)
            .filter(|word| word.kind == TokenKind::Word && word.start == token.end)
        else {
            continue;
        };
        let word_text: &str = word.text(sql);
        if DECLARATION_WORDS.contains(&word_text) {
            continue;
        }
        let kinded: bool = matches!(word_text, "sql" | "py")
            && scanned
                .get(index + 2)
                .is_some_and(|dot| dot.is(sql, ".") && dot.start == word.end);
        if kinded {
            let Some(name) = scanned
                .get(index + 3)
                .filter(|name| name.kind == TokenKind::Word)
            else {
                continue;
            };
            let Some(open) = scanned.get(index + 4).filter(|open| open.is(sql, "(")) else {
                continue;
            };
            let Some(close) = closing_token(sql, &scanned, index + 4) else {
                continue;
            };
            let end: usize = scanned[close].end;
            let name_text: String = name.text(sql).to_owned();
            found.push(if word_text == SQL_KIND_WORD {
                AtConstruct::Sql {
                    name: name_text,
                    start: token.start,
                    end,
                    arguments: (open.end, scanned[close].start),
                }
            } else {
                AtConstruct::Python {
                    name: name_text,
                    start: token.start,
                    end,
                }
            });
            continue;
        }
        if scanned.get(index + 2).is_some_and(|open| open.is(sql, "(")) {
            found.push(AtConstruct::Bare {
                name: word_text.to_owned(),
                start: token.start,
            });
        }
    }
    Ok(found)
}

/// Each outer SQL macro call of `sql` and whether it stands in a Python macro call's arguments.
pub(crate) fn outer_sql_calls(constructs: &[AtConstruct]) -> Vec<(&AtConstruct, bool)> {
    let mut found: Vec<(&AtConstruct, bool)> = Vec::new();
    let mut sql_until: usize = 0;
    let mut python_until: usize = 0;
    for construct in constructs {
        match construct {
            AtConstruct::Sql { start, end, .. } => {
                if *start < sql_until {
                    continue;
                }
                sql_until = *end;
                found.push((construct, *start < python_until));
            }
            AtConstruct::Python { start, end, .. } => {
                if *start >= python_until && *start >= sql_until {
                    python_until = *end;
                }
            }
            AtConstruct::Bare { .. } => {}
        }
    }
    found
}
