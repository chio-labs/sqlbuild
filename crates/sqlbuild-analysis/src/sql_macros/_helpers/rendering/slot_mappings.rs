//! A call's `relation.slot := ...` arguments, checked and bound to the macro's declared slots.

use crate::sql_macros::_helpers::parsing::header::{split_top_level, unquoted};
use crate::sql_macros::_helpers::parsing::lexing::{Token, TokenKind, closing_token, tokens};
use crate::sql_macros::_helpers::rendering::arguments::parameter_names;
use crate::sql_macros::constants::ARGUMENT_CODE;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::models::{CallArgument, ParameterKind, SlotMapping, SqlMacroDefinition};

/// The slots each parameter's call maps, by parameter index, or why the mappings are wrong.
pub(crate) fn slot_mappings(
    definition: &SqlMacroDefinition,
    arguments: &[&CallArgument],
) -> Result<Vec<Vec<SlotMapping>>, SqlMacroError> {
    let name: &str = &definition.name;
    let mut mapped: Vec<Vec<SlotMapping>> = vec![Vec::new(); definition.parameters.len()];
    for argument in arguments {
        let (Some(relation), Some(slot)) = (&argument.name, &argument.slot) else {
            continue;
        };
        let Some(index) = definition
            .parameters
            .iter()
            .position(|parameter| parameter.name.eq_ignore_ascii_case(relation))
        else {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!("macro {name}() has no argument {relation}"),
            )
            .helped(format!("its arguments are {}", parameter_names(definition))));
        };
        let parameter = &definition.parameters[index];
        let relation: &str = &parameter.name;
        let ParameterKind::Relation { columns, groups } = &parameter.kind else {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!(
                    "argument {relation} of macro {name}() is {}, not a RELATION; only a RELATION argument has slots to map",
                    parameter.kind.label()
                ),
            )
            .helped(format!("pass it as {relation} := <value>")));
        };
        let declared: Option<(String, bool)> = groups
            .iter()
            .find(|group| group.eq_ignore_ascii_case(slot))
            .map(|group| (group.clone(), true))
            .or_else(|| {
                columns
                    .iter()
                    .find(|(column, _)| column.eq_ignore_ascii_case(slot))
                    .map(|(column, _)| (column.clone(), false))
            });
        let Some((slot, group)) = declared else {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!("RELATION argument {relation} of macro {name}() has no slot {slot}"),
            )
            .helped(format!("its slots are {}", slot_list(columns, groups))));
        };
        if mapped[index]
            .iter()
            .any(|known| known.slot.eq_ignore_ascii_case(&slot))
        {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!("slot {relation}.{slot} of macro {name}() is mapped twice"),
            ));
        }
        let shown: String = format!("{relation}.{slot}");
        let mapped_columns: Vec<String> = if group {
            group_columns(name, &shown, argument.text.trim())?
        } else {
            vec![single_column(name, &shown, argument.text.trim())?]
        };
        mapped[index].push(SlotMapping {
            slot,
            columns: mapped_columns,
            group,
        });
    }
    for (index, parameter) in definition.parameters.iter().enumerate() {
        let ParameterKind::Relation { columns, groups } = &parameter.kind else {
            continue;
        };
        let relation: &str = &parameter.name;
        let given: Vec<SlotMapping> = std::mem::take(&mut mapped[index]);
        let mut ordered: Vec<SlotMapping> = Vec::with_capacity(given.len());
        for (column, _) in columns {
            if let Some(found) = mapping_of(&given, column) {
                ordered.push(found.clone());
            }
        }
        for group in groups {
            let Some(found) = mapping_of(&given, group).cloned() else {
                return Err(SqlMacroError::new(
                    ARGUMENT_CODE,
                    format!("call to macro {name}() is missing slot {relation}.{group} COLUMNS"),
                )
                .helped(format!(
                    "map it to the passed relation's columns, such as {relation}.{group} := (product_id)"
                )));
            };
            ordered.push(found);
        }
        check_overlaps(name, relation, columns, &ordered)?;
        mapped[index] = ordered;
    }
    Ok(mapped)
}

/// The mapping the call made for `slot`, if it made one.
fn mapping_of<'m>(mappings: &'m [SlotMapping], slot: &str) -> Option<&'m SlotMapping> {
    mappings
        .iter()
        .find(|mapping| mapping.slot.eq_ignore_ascii_case(slot))
}

/// The one column name a single-column slot is mapped to.
fn single_column(name: &str, shown: &str, text: &str) -> Result<String, SqlMacroError> {
    match tokens(text).as_deref() {
        Ok([column]) if matches!(column.kind, TokenKind::Word | TokenKind::Quoted) => {
            Ok(column.text(text).to_owned())
        }
        _ => Err(SqlMacroError::new(
            ARGUMENT_CODE,
            format!("slot {shown} of macro {name}() takes one column name of the passed relation; got {text}"),
        )
        .helped(format!("map it to a column, such as {shown} := order_total; a slot reads the column as it is, so compute expressions in the relation you pass"))),
    }
}

/// The column names a `COLUMNS` slot is mapped to: a parenthesised list, never empty.
fn group_columns(name: &str, shown: &str, text: &str) -> Result<Vec<String>, SqlMacroError> {
    let invalid = || {
        SqlMacroError::new(
            ARGUMENT_CODE,
            format!("slot {shown} of macro {name}() takes a parenthesised list of column names of the passed relation; got {text}"),
        )
        .helped(format!("map it to columns, such as {shown} := (product_id, region)"))
    };
    let scanned: Vec<Token> = tokens(text).map_err(|_| invalid())?;
    let wrapped: bool = scanned.first().is_some_and(|open| open.is(text, "("))
        && closing_token(text, &scanned, 0) == Some(scanned.len() - 1);
    if !wrapped {
        return Err(invalid());
    }
    let inner: &[Token] = &scanned[1..scanned.len() - 1];
    if inner.is_empty() {
        return Err(SqlMacroError::new(
            ARGUMENT_CODE,
            format!("slot {shown} of macro {name}() needs at least one column; got {text}"),
        )
        .helped(format!(
            "map it to columns, such as {shown} := (product_id)"
        )));
    }
    let items: Vec<&[Token]> = split_top_level(text, inner);
    let commas: usize = inner.iter().filter(|token| token.is(text, ",")).count();
    if items.len() != commas + 1 {
        return Err(invalid());
    }
    let mut columns: Vec<String> = Vec::with_capacity(items.len());
    for item in items {
        let [column] = item else {
            return Err(invalid());
        };
        if !matches!(column.kind, TokenKind::Word | TokenKind::Quoted) {
            return Err(invalid());
        }
        let column: String = column.text(text).to_owned();
        if columns.iter().any(|known| same_column(known, &column)) {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!("column {column} is listed twice in slot {shown} of macro {name}()"),
            ));
        }
        columns.push(column);
    }
    Ok(columns)
}

/// Rejects groups of one relation sharing a column, or a group holding a single slot's column.
fn check_overlaps(
    name: &str,
    relation: &str,
    columns: &[(String, String)],
    mappings: &[SlotMapping],
) -> Result<(), SqlMacroError> {
    let groups: Vec<&SlotMapping> = mappings.iter().filter(|mapping| mapping.group).collect();
    for (position, group) in groups.iter().enumerate() {
        for other in &groups[position + 1..] {
            if let Some(column) = shared_column(group, other) {
                return Err(SqlMacroError::new(
                    ARGUMENT_CODE,
                    format!(
                        "slots {relation}.{} and {relation}.{} of macro {name}() both group column {column}; groups of one relation may not overlap",
                        group.slot, other.slot
                    ),
                )
                .helped("list each column in at most one group"));
            }
        }
    }
    for (slot, _) in columns {
        let read: String = mappings
            .iter()
            .find(|mapping| !mapping.group && mapping.slot.eq_ignore_ascii_case(slot))
            .map_or_else(|| slot.clone(), |mapping| mapping.columns[0].clone());
        if let Some(group) = groups.iter().find(|group| groups_column(group, &read)) {
            return Err(SqlMacroError::new(
                ARGUMENT_CODE,
                format!(
                    "column {read} is in slot {relation}.{} and also fills single-column slot {relation}.{slot} of macro {name}(); a grouped column may not fill a single-column slot",
                    group.slot
                ),
            )
            .helped(format!(
                "remove {read} from {relation}.{}, or map {relation}.{slot} to another column",
                group.slot
            )));
        }
    }
    Ok(())
}

/// The first column `group` shares with `other`, if any.
fn shared_column<'g>(group: &'g SlotMapping, other: &SlotMapping) -> Option<&'g String> {
    group
        .columns
        .iter()
        .find(|column| groups_column(other, column))
}

/// Whether `group` lists `column`.
fn groups_column(group: &SlotMapping, column: &str) -> bool {
    group.columns.iter().any(|known| same_column(known, column))
}

/// Whether two column names written by a caller name the same column.
pub(crate) fn same_column(left: &str, right: &str) -> bool {
    unquoted(left).eq_ignore_ascii_case(&unquoted(right))
}

/// A relation's slots as messages list them.
pub(crate) fn slot_list(columns: &[(String, String)], groups: &[String]) -> String {
    columns
        .iter()
        .map(|(column, data_type)| format!("{column} {data_type}"))
        .chain(groups.iter().map(|group| format!("{group} COLUMNS")))
        .collect::<Vec<String>>()
        .join(", ")
}
