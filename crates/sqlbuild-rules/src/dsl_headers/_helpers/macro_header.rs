//! The canonical layout of a SQL macro's `MACRO (...)` header, and whether a layout kept its meaning.

use sqlbuild_analysis::sql_macros::main::parse_sql_macro::parse_sql_macro;
use sqlbuild_analysis::sql_macros::models::SqlMacroDefinition;
use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::dsl_headers::_helpers::quoted::quoted_value_end;
use crate::dsl_headers::_helpers::text::{slice, string, tail};
use crate::dsl_headers::constants::{
    HEADER_INDENT, HEADER_TERMINATOR, QUOTES, SQL_MACRO_HEADER_KIND,
};
use crate::dsl_headers::models::HeaderSpan;

/// `text` with every `MACRO` header laid out canonically within `line_width`.
pub(crate) fn layout_macro_headers(
    text: &[char],
    headers: &[HeaderSpan],
    line_width: i64,
) -> Vec<char> {
    let width: usize = usize::try_from(line_width).unwrap_or(usize::MAX);
    let mut updated: Vec<char> = Vec::with_capacity(text.len());
    let mut cursor: usize = 0;
    for header in headers {
        if header.kind != SQL_MACRO_HEADER_KIND {
            continue;
        }
        let original: &[char] = slice(text, header.start, header.end);
        let Some(laid_out) = macro_header(original, width) else {
            continue;
        };
        updated.extend(slice(text, cursor, header.start));
        updated.extend(laid_out.chars());
        cursor = header.end;
    }
    updated.extend(tail(text, cursor));
    updated
}

/// One header on one line if authored so and it fits, else one item per line; `None` if unreadable.
fn macro_header(header: &[char], width: usize) -> Option<String> {
    let open: usize = header.iter().position(|character| *character == '(')?;
    let close: usize = header.iter().rposition(|character| *character == ')')?;
    if close <= open || has_comment(header) {
        return None;
    }
    let keyword: String = string(&header[..open]).trim_end().to_owned();
    let closing: String = string(&header[close + 1..]).trim().to_owned();
    if !closing.is_empty() && closing != HEADER_TERMINATOR {
        return None;
    }
    let items: Vec<String> = split_items(&header[open + 1..close])?;
    let single: String = format!("{keyword} ({}){closing}", items.join(", "));
    if !header.contains(&'\n') && single.chars().count() <= width {
        return Some(single);
    }
    let mut lines: Vec<String> = vec![format!("{keyword} (")];
    for item in &items {
        lines.extend(item_lines(item, HEADER_INDENT, width));
    }
    lines.push(format!("){closing}"));
    Some(lines.join("\n"))
}

/// The lines of one item at `indent`, ending in a comma; a list too wide breaks one per line.
fn item_lines(item: &str, indent: &str, width: usize) -> Vec<String> {
    let line: String = format!("{indent}{item},");
    if line.chars().count() <= width {
        return vec![line];
    }
    let characters: Vec<char> = item.chars().collect();
    let Some((open, close)) = outer_list(&characters) else {
        return vec![line];
    };
    let Some(entries) = split_items(&characters[open + 1..close]) else {
        return vec![line];
    };
    let nested: String = format!("{indent}{HEADER_INDENT}");
    let mut lines: Vec<String> = vec![format!("{indent}{}", string(&characters[..=open]))];
    for entry in &entries {
        lines.extend(item_lines(entry, &nested, width));
    }
    lines.push(format!("{indent}{},", string(&characters[close..])));
    lines
}

/// The first top-level `(` of `item` and its closing `)` when that ends the item.
fn outer_list(item: &[char]) -> Option<(usize, usize)> {
    let open: usize = item.iter().position(|character| *character == '(')?;
    let mut depth: usize = 0;
    let mut index: usize = open;
    while index < item.len() {
        let character: char = item[index];
        if QUOTES.contains(&character) {
            index = quoted_value_end(item, index);
            continue;
        }
        match character {
            '(' | '[' | '{' => depth += 1,
            ')' | ']' | '}' => {
                depth -= 1;
                if depth == 0 {
                    return (index + 1 == item.len()).then_some((open, index));
                }
            }
            _ => {}
        }
        index += 1;
    }
    None
}

/// The comma-separated items of `inner` with normalised whitespace, or `None` if unbalanced.
fn split_items(inner: &[char]) -> Option<Vec<String>> {
    let mut items: Vec<String> = Vec::new();
    let mut current: String = String::new();
    let mut depth: usize = 0;
    let mut index: usize = 0;
    let mut pending_space: bool = false;
    while index < inner.len() {
        let character: char = inner[index];
        if python_isspace(character) {
            pending_space = !current.is_empty();
            index += 1;
            continue;
        }
        if character == ',' && depth == 0 {
            items.push(std::mem::take(&mut current));
            pending_space = false;
            index += 1;
            continue;
        }
        let closes: bool = matches!(character, ')' | ']' | '}');
        if closes {
            current.truncate(current.trim_end_matches([',', ' ']).len());
        }
        let after_open: bool = current.ends_with(['(', '[', '{']);
        if pending_space && !closes && !after_open && character != ',' {
            current.push(' ');
        }
        pending_space = false;
        if QUOTES.contains(&character) {
            let end: usize = quoted_value_end(inner, index);
            current.push_str(&string(&inner[index..end]));
            index = end;
            continue;
        }
        match character {
            '(' | '[' | '{' => depth += 1,
            ')' | ']' | '}' => depth = depth.checked_sub(1)?,
            _ => {}
        }
        current.push(character);
        if character == ',' {
            current.push(' ');
            while inner
                .get(index + 1)
                .is_some_and(|next| python_isspace(*next))
            {
                index += 1;
            }
        }
        index += 1;
    }
    if depth != 0 {
        return None;
    }
    let current: String = current.trim_end_matches([',', ' ']).to_owned();
    if !current.is_empty() {
        items.push(current);
    }
    let items: Vec<String> = items
        .into_iter()
        .map(|item| item.trim_end().to_owned())
        .collect();
    (!items.iter().any(String::is_empty)).then_some(items)
}

/// Whether the header holds a comment outside its quoted values.
fn has_comment(header: &[char]) -> bool {
    let mut index: usize = 0;
    while index < header.len() {
        let character: char = header[index];
        if QUOTES.contains(&character) {
            index = quoted_value_end(header, index);
            continue;
        }
        if matches!(
            (character, header.get(index + 1)),
            ('-', Some('-')) | ('/', Some('*'))
        ) {
            return true;
        }
        index += 1;
    }
    false
}

/// The macro `text` defines with every line and column cleared, if it parses.
fn positionless_macro(text: &[char]) -> Option<SqlMacroDefinition> {
    let Ok(mut definition) = parse_sql_macro("formatted", "formatted.sql", &string(text)) else {
        return None;
    };
    definition.body_line = 0;
    definition.body_column = 0;
    for parameter in &mut definition.parameters {
        parameter.line = 0;
        parameter.column = 0;
    }
    Some(definition)
}

/// Whether `before` and `after` both parse to the same macro; a parse failure equals nothing.
pub(crate) fn same_macro(before: &[char], after: &[char]) -> bool {
    positionless_macro(before)
        .is_some_and(|definition| positionless_macro(after) == Some(definition))
}

/// Whether `before` defines a macro that `after` no longer defines the same.
pub(crate) fn changes_macro(before: &[char], after: &[char]) -> bool {
    positionless_macro(before)
        .is_some_and(|definition| positionless_macro(after) != Some(definition))
}
