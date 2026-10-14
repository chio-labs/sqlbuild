//! Exact authored marker recognition at a byte offset.

use crate::planner_scenario::constants::{DBT_REF_MARKER, MARKERS};
use sqlbuild_sqltext::resolution::main::quoted_name::quoted_name;

pub(crate) fn marker_at(sql: &str, kind: usize) -> Option<(usize, String)> {
    let tail = sql.strip_prefix(MARKERS[kind])?;
    let (first, tail) = quoted_name(tail)?;
    if tail.starts_with(')') {
        return Some((sql.len() - tail.len() + 1, first.to_owned()));
    }
    if kind != DBT_REF_MARKER {
        return None;
    }
    let tail = tail
        .trim_start_matches(python_whitespace)
        .strip_prefix(',')?;
    let (second, tail) = quoted_name(tail.trim_start_matches(python_whitespace))?;
    tail.starts_with(')')
        .then(|| (sql.len() - tail.len() + 1, format!("{first}__{second}")))
}

fn python_whitespace(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}
