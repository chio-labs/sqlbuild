//! Token-span CTE renaming for dialects that reject a nested WITH.

use crate::compiler::_helpers::sql_tests::cte_slices::{
    SliceDialect, WithSlices, opaque_end, read_identifier,
};
use sqlbuild_sqltext::sql_scan::main::comment_end::comment_end;
use sqlbuild_sqltext::sql_scan::main::skip_whitespace::skip_whitespace;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

const DOT: &str = ".";

/// One lexical token of a statement: its byte span and, for identifiers, its case-folded key.
#[derive(Debug, PartialEq, Eq)]
struct Token {
    start: usize,
    end: usize,
    key: Option<String>,
    comment: bool,
}

/// One CTE of a split statement to rename: its index in the WITH list and its new name.
pub(crate) struct CteRename<'a> {
    pub(crate) index: usize,
    pub(crate) name: &'a str,
}

/// Rename CTEs and their relation references by token span; `None` when not provably safe.
pub(crate) fn rename_ctes(
    sql: &str,
    split: &WithSlices<'_>,
    renames: &[CteRename<'_>],
    dialect: SliceDialect,
) -> Option<String> {
    let tokens = match tokens(sql, dialect) {
        Ok(tokens) => tokens,
        Err(_) => return None,
    };
    let mut replaced: Vec<(usize, &str)> = Vec::new();
    for rename in renames {
        let cte = split.ctes.get(rename.index)?;
        let definition = tokens
            .iter()
            .position(|token| token.start == cte.header_start)?;
        let mut multipart_object = false;
        let mut qualifier = false;
        for (position, token) in tokens.iter().enumerate() {
            if token.key.as_deref() != Some(cte.key.as_str()) {
                continue;
            }
            if position < definition {
                return None;
            }
            let usage = if position == definition {
                Usage::Relation
            } else {
                usage(sql, &tokens, position)?
            };
            multipart_object |= usage == Usage::MultipartObject;
            qualifier |= usage == Usage::Qualifier;
            if matches!(usage, Usage::Relation | Usage::Qualifier) {
                replaced.push((position, rename.name));
            }
        }
        if multipart_object && qualifier {
            return None;
        }
    }
    replaced.sort_unstable();
    let mut renamed = String::with_capacity(sql.len());
    let mut cursor = 0;
    for (position, name) in &replaced {
        let token = &tokens[*position];
        renamed.push_str(&sql[cursor..token.start]);
        renamed.push_str(name);
        cursor = token.end;
    }
    renamed.push_str(&sql[cursor..]);
    let renamed_tokens = match self::tokens(&renamed, dialect) {
        Ok(renamed_tokens) => renamed_tokens,
        Err(_) => return None,
    };
    preserves_tokens((sql, &tokens), (&renamed, &renamed_tokens), &replaced).then_some(renamed)
}

/// Case-folded names of every CTE a statement defines at any depth; `None` when unscannable.
pub(crate) fn defined_cte_keys(sql: &str, dialect: SliceDialect) -> Option<Vec<String>> {
    let tokens = match tokens(sql, dialect) {
        Ok(tokens) => tokens,
        Err(_) => return None,
    };
    let code: Vec<&Token> = tokens.iter().filter(|token| !token.comment).collect();
    let text = |index: usize| code.get(index).map(|token| &sql[token.start..token.end]);
    let keyword = |index: usize, word: &str| {
        code.get(index)
            .and_then(|token| token.key.as_deref())
            .is_some_and(|key| key == word)
    };
    let in_with_list = with_list_commas(sql, &code);
    let mut keys: Vec<String> = Vec::new();
    for (index, token) in code.iter().enumerate() {
        let Some(key) = token.key.as_deref() else {
            continue;
        };
        let opens_list = index > 0
            && (keyword(index - 1, "with")
                || keyword(index - 1, "recursive")
                || (text(index - 1) == Some(",") && in_with_list[index - 1]));
        if !opens_list {
            continue;
        }
        let mut next = index + 1;
        if text(next) == Some("(") {
            let mut depth = 0usize;
            while let Some(part) = text(next) {
                depth = match part {
                    "(" => depth + 1,
                    ")" => depth.saturating_sub(1),
                    _ => depth,
                };
                next += 1;
                if depth == 0 {
                    break;
                }
            }
        }
        if !keyword(next, "as") {
            continue;
        }
        next += 1;
        if keyword(next, "not") {
            next += 1;
        }
        if keyword(next, "materialized") {
            next += 1;
        }
        if text(next) == Some("(") {
            keys.push(key.to_string());
        }
    }
    Some(keys)
}

/// Clause keywords that end a WITH list at their parenthesis depth.
const LIST_ENDING_CLAUSES: &[&str] = &[
    "select",
    "from",
    "where",
    "group",
    "having",
    "qualify",
    "order",
    "limit",
    "window",
    "union",
    "except",
    "intersect",
    "minus",
    "values",
    "insert",
    "update",
    "delete",
    "merge",
];

/// Whether each token sits directly in a WITH list, so a comma there separates CTEs.
fn with_list_commas(sql: &str, code: &[&Token]) -> Vec<bool> {
    let mut lists: Vec<bool> = vec![false];
    let mut in_list: Vec<bool> = Vec::with_capacity(code.len());
    for token in code {
        match &sql[token.start..token.end] {
            "(" => lists.push(false),
            ")" => {
                if lists.len() > 1 {
                    let _ = lists.pop();
                }
            }
            _ => {
                if let (Some(key), Some(current)) = (token.key.as_deref(), lists.last_mut()) {
                    if key == "with" {
                        *current = true;
                    } else if LIST_ENDING_CLAUSES.contains(&key) {
                        *current = false;
                    }
                }
            }
        }
        in_list.push(lists.last().copied().unwrap_or(false));
    }
    in_list
}

/// How one occurrence of a renamed CTE's name is used.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Usage {
    /// A relation reference to the CTE, renamed.
    Relation,
    /// A column qualifier naming the CTE, renamed.
    Qualifier,
    /// The leading part of a multipart object name such as `final.dbo.orders`, kept.
    MultipartObject,
    /// A trailing part of a qualified name such as `t.final`, kept.
    QualifiedPart,
}

/// Classify one occurrence, or `None` when its use is ambiguous.
fn usage(sql: &str, tokens: &[Token], position: usize) -> Option<Usage> {
    let previous = significant(tokens, position, -1);
    let next = significant(tokens, position, 1);
    if previous.is_some_and(|token| is_dot(sql, token)) {
        return Some(Usage::QualifiedPart);
    }
    let relation_position = matches!(
        previous.and_then(|token| token.key.as_deref()),
        Some("from" | "join" | "apply")
    );
    let dotted = next.is_some_and(|token| is_dot(sql, token));
    match (relation_position, dotted) {
        (true, true) => Some(Usage::MultipartObject),
        (true, false) => Some(Usage::Relation),
        (false, true) => Some(Usage::Qualifier),
        (false, false) => None,
    }
}

fn is_dot(sql: &str, token: &Token) -> bool {
    token.key.is_none() && !token.comment && &sql[token.start..token.end] == DOT
}

fn significant(tokens: &[Token], position: usize, step: isize) -> Option<&Token> {
    let mut index = position.checked_add_signed(step)?;
    while let Some(token) = tokens.get(index) {
        if !token.comment {
            return Some(token);
        }
        index = index.checked_add_signed(step)?;
    }
    None
}

/// Require every untouched token of the renamed SQL to be byte-identical to the original.
fn preserves_tokens(
    (sql, original): (&str, &[Token]),
    (renamed_sql, renamed): (&str, &[Token]),
    replaced: &[(usize, &str)],
) -> bool {
    if renamed.len() != original.len() {
        return false;
    }
    for (position, (before, after)) in original.iter().zip(renamed).enumerate() {
        let after_text = &renamed_sql[after.start..after.end];
        let expected = replaced
            .iter()
            .find(|(index, _)| *index == position)
            .map_or(&sql[before.start..before.end], |(_, name)| *name);
        if after_text != expected {
            return false;
        }
    }
    true
}

fn tokens(sql: &str, dialect: SliceDialect) -> Result<Vec<Token>, Unclosed> {
    let bytes = sql.as_bytes();
    let mut tokens: Vec<Token> = Vec::new();
    let mut index = skip_whitespace(sql, 0);
    while index < bytes.len() {
        let comment = comment_end(bytes, index)?;
        let (end, key) = if let Some(end) = comment {
            (end, None)
        } else if let Some((key, end)) = read_identifier(sql, index, dialect)? {
            (end, Some(key))
        } else if let Some(end) = opaque_end(bytes, index, dialect)? {
            (end, None)
        } else {
            (
                index + sql[index..].chars().next().map_or(1, char::len_utf8),
                None,
            )
        };
        tokens.push(Token {
            start: index,
            end,
            key,
            comment: comment.is_some(),
        });
        index = skip_whitespace(sql, end);
    }
    Ok(tokens)
}
