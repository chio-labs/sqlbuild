//! Slot reads in a SQL macro body, `@relation.slot` and `alias.@relation.slot`, and their places.

use crate::sql_macros::_helpers::parsing::header::unquoted;
use crate::sql_macros::_helpers::parsing::lexing::{Token, TokenKind};
use crate::sql_macros::_helpers::parsing::parameters::ParameterReference;
use crate::sql_macros::constants::{
    GROUP_POSITIONS, INVALID_DEFINITION_CODE, PARAMETER_REFERENCE_CODE,
};
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{ParameterKind, SqlMacroDefinition};

/// Words after which a list item ends without being renamed, ordered or extended.
const LIST_ENDS: [&str; 18] = [
    "FROM",
    "WHERE",
    "GROUP",
    "HAVING",
    "QUALIFY",
    "WINDOW",
    "ORDER",
    "LIMIT",
    "OFFSET",
    "FETCH",
    "UNION",
    "INTERSECT",
    "EXCEPT",
    "MINUS",
    "ROWS",
    "RANGE",
    "GROUPS",
    "INTO",
];
/// Words that end the search for a list's head: the read is not in a list a group may fill.
const NOT_LIST_HEADS: [&str; 19] = [
    "FROM",
    "WHERE",
    "ON",
    "HAVING",
    "QUALIFY",
    "WHEN",
    "THEN",
    "ELSE",
    "VALUES",
    "SET",
    "LIMIT",
    "OFFSET",
    "JOIN",
    "WITH",
    "RETURNING",
    "INTO",
    "LATERAL",
    "UNION",
    "INTERSECT",
];
/// The tokens one alias step takes back: a name and its dot.
const ALIAS_STEP: usize = 2;
/// The words before `BY` that open a list a group may fill.
const BY_LISTS: [&str; 3] = ["PARTITION", "GROUP", "ORDER"];

/// One read of a declared slot through a `RELATION` parameter.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SlotRead {
    /// Byte span of the whole read, from its alias prefix, if any, to the slot's name.
    pub(crate) start: usize,
    pub(crate) end: usize,
    /// Byte span of the alias prefix, as `s.` in `s.@weekly.order_count`.
    pub(crate) prefix: Option<(usize, usize)>,
    /// Index of the `@relation` reference among the body's parameter references.
    pub(crate) reference: usize,
    /// Token indexes of the read's first and last tokens.
    pub(crate) tokens: (usize, usize),
    /// The relation parameter and slot names as the macro declares them.
    pub(crate) relation: String,
    pub(crate) slot: String,
    /// The slot's name as the body writes it.
    pub(crate) written: String,
    pub(crate) group: bool,
    /// The read stands in `USING (...)`, unqualified, and may name an undeclared column.
    pub(crate) in_using: bool,
}

/// The list a read is a whole item of.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ListHead {
    Select,
    By,
    Using,
}

/// Every slot read of `body`, or why an aliased read names no slot.
pub(crate) fn slot_reads(
    definition: &SqlMacroDefinition,
    (body, scanned, references): (&str, &[Token], &[ParameterReference]),
) -> Result<Vec<SlotRead>, (usize, SqlMacroError)> {
    let mut reads: Vec<SlotRead> = Vec::new();
    for (position, reference) in references.iter().enumerate() {
        let Some(parameter) = definition.parameter(&reference.name) else {
            continue;
        };
        let ParameterKind::Relation { columns, groups } = &parameter.kind else {
            continue;
        };
        let name_token: usize = reference.token;
        let prefix_token: Option<usize> = prefix_start(body, scanned, name_token - 1);
        let slot_token: Option<&Token> = scanned
            .get(name_token + 1)
            .filter(|dot| dot.is(body, ".") && dot.start == scanned[name_token].end)
            .and_then(|dot| {
                scanned.get(name_token + 2).filter(|word| {
                    matches!(word.kind, TokenKind::Word | TokenKind::Quoted)
                        && word.start == dot.end
                })
            });
        let relation: &str = &parameter.name;
        let prefix: Option<(usize, usize)> =
            prefix_token.map(|first| (scanned[first].start, reference.start));
        let shown_prefix: &str = prefix.map_or("", |(start, end)| &body[start..end]);
        let Some(slot_token) = slot_token else {
            if prefix.is_some() {
                return Err((
                    reference.start,
                    SqlMacroError::new(
                        PARAMETER_REFERENCE_CODE,
                        format!("{shown_prefix}@{relation} in the body of macro {}() reads RELATION argument {relation} through an alias without naming a slot", definition.name),
                    )
                    .helped(format!("name a slot, as in {shown_prefix}@{relation}.<slot>; its slots are {}", slot_names(columns, groups))),
                ));
            }
            continue;
        };
        let written: String = slot_token.text(body).to_owned();
        let bare: String = unquoted(&written);
        let declared: Option<(&str, bool)> = groups
            .iter()
            .find(|group| group.eq_ignore_ascii_case(&bare))
            .map(|group| (group.as_str(), true))
            .or_else(|| {
                columns
                    .iter()
                    .find(|(column, _)| column.eq_ignore_ascii_case(&bare))
                    .map(|(column, _)| (column.as_str(), false))
            });
        let first: usize = prefix_token.unwrap_or(name_token - 1);
        let in_using: bool =
            prefix.is_none() && list_head(body, scanned, first) == Some(ListHead::Using);
        let declared: Option<(&str, bool)> = match declared {
            None if in_using => Some((written.as_str(), false)),
            declared => declared,
        };
        let Some((slot, group)) = declared else {
            if prefix.is_some() {
                return Err((
                    reference.start,
                    SqlMacroError::new(
                        PARAMETER_REFERENCE_CODE,
                        format!("{shown_prefix}@{relation}.{written} in the body of macro {}() names no slot of RELATION argument {relation}", definition.name),
                    )
                    .helped(format!("its slots are {}; declare {written} in {relation} RELATION (...) or fix the name", slot_names(columns, groups))),
                ));
            }
            continue;
        };
        reads.push(SlotRead {
            in_using,
            start: prefix.map_or(reference.start, |(start, _)| start),
            end: slot_token.end,
            prefix,
            reference: position,
            tokens: (first, name_token + 2),
            relation: relation.to_owned(),
            slot: slot.to_owned(),
            written,
            group,
        });
    }
    Ok(reads)
}

/// The first token of the alias chain that qualifies the `@` at token `at`, if one does.
pub(crate) fn prefix_start(body: &str, scanned: &[Token], at: usize) -> Option<usize> {
    let mut first: Option<usize> = None;
    let mut cursor: usize = at;
    while cursor >= ALIAS_STEP {
        let dot: &Token = &scanned[cursor - 1];
        let word: &Token = &scanned[cursor - ALIAS_STEP];
        let joined: bool = dot.is(body, ".")
            && dot.end == scanned[cursor].start
            && matches!(word.kind, TokenKind::Word | TokenKind::Quoted)
            && word.end == dot.start;
        if !joined {
            break;
        }
        first = Some(cursor - ALIAS_STEP);
        cursor -= ALIAS_STEP;
    }
    first
}

fn slot_names(columns: &[(String, String)], groups: &[String]) -> String {
    columns
        .iter()
        .map(|(column, _)| column.as_str())
        .chain(groups.iter().map(String::as_str))
        .collect::<Vec<&str>>()
        .join(", ")
}

/// Rejects a `COLUMNS` slot read anywhere but as a whole item of a list it may fill.
pub(crate) fn check_group_positions(
    definition: &SqlMacroDefinition,
    (body, scanned): (&str, &[Token]),
    reads: &[SlotRead],
) -> Result<(), (usize, SqlMacroError)> {
    for read in reads.iter().filter(|read| read.group) {
        if !ends_item(body, scanned, read.tokens.1)
            || list_head(body, scanned, read.tokens.0).is_none()
        {
            let shown: &str = &body[read.start..read.end];
            return Err((
                read.start,
                SqlMacroError::new(
                    INVALID_DEFINITION_CODE,
                    format!(
                        "COLUMNS slot {}.{} is read as {shown} in macro {}() where a list item cannot stand; a COLUMNS slot is pasted as its columns, comma-separated, so it stands only as a whole item of {GROUP_POSITIONS}",
                        read.relation, read.slot, definition.name
                    ),
                )
                .helped(format!(
                    "a group takes no expression, alias, ordering or indexing; read one column through a single-column slot declared as <name> <type> in {} RELATION (...)",
                    read.relation
                )),
            ));
        }
    }
    Ok(())
}

/// Whether the read whose last token is `last` ends its list item.
fn ends_item(body: &str, scanned: &[Token], last: usize) -> bool {
    match scanned.get(last + 1) {
        None => true,
        Some(next) if next.is(body, ",") || next.is(body, ")") || next.is(body, ";") => true,
        Some(next) => LIST_ENDS.iter().any(|keyword| next.is_word(body, keyword)),
    }
}

/// The list a group may fill whose item starts at token `first`, after its head or a comma.
fn list_head(body: &str, scanned: &[Token], first: usize) -> Option<ListHead> {
    let previous: &Token = first.checked_sub(1).map(|index| &scanned[index])?;
    let starts_item: bool = previous.is(body, ",")
        || previous.is(body, "(")
        || previous.is_word(body, "SELECT")
        || previous.is_word(body, "DISTINCT")
        || previous.is_word(body, "ALL")
        || previous.is_word(body, "BY");
    if !starts_item {
        return None;
    }
    let mut depth: usize = 0;
    let mut index: usize = first;
    while index > 0 {
        index -= 1;
        let token: &Token = &scanned[index];
        if token.is(body, ")") || token.is_word(body, "END") {
            depth += 1;
            continue;
        }
        if token.is(body, "(") || token.is_word(body, "CASE") {
            if depth > 0 {
                depth -= 1;
                continue;
            }
            let using: bool =
                token.is(body, "(") && index > 0 && scanned[index - 1].is_word(body, "USING");
            return using.then_some(ListHead::Using);
        }
        if depth > 0 || token.kind != TokenKind::Word {
            continue;
        }
        if token.is_word(body, "SELECT") {
            return Some(ListHead::Select);
        }
        if token.is_word(body, "BY") {
            let listed: bool = index > 0
                && BY_LISTS
                    .iter()
                    .any(|keyword| scanned[index - 1].is_word(body, keyword));
            return listed.then_some(ListHead::By);
        }
        if NOT_LIST_HEADS
            .iter()
            .any(|keyword| token.is_word(body, keyword))
        {
            return None;
        }
    }
    None
}
