//! Locate planner reference markers with their historical lexical policy.

use crate::resolution::constants::EXTERNAL_REFERENCE;
use crate::resolution::main::quoted_name::quoted_name;
use crate::resolution::models::ReferenceSpan;

/// Locate exact reference markers, retaining the external-reference whitespace grammar.
pub fn reference_spans(sql: &str, kind: &str) -> Vec<ReferenceSpan> {
    let prefix = format!("__{kind}(");
    let external = kind == EXTERNAL_REFERENCE;
    let mut spans: Vec<ReferenceSpan> = Vec::new();
    let mut consumed = 0;
    for (start, _) in sql.char_indices() {
        if start < consumed {
            continue;
        }
        let Some(candidate) = sql.get(start..start + prefix.len()) else {
            continue;
        };
        if candidate != prefix && !(external && candidate.eq_ignore_ascii_case(&prefix)) {
            continue;
        }
        let mut tail = &sql[start + prefix.len()..];
        if external {
            tail = tail.trim_start();
        }
        let Some((first, rest)) = quoted_name(tail) else {
            continue;
        };
        tail = if external { rest.trim_start() } else { rest };
        let mut second = None;
        if external && tail.starts_with(',') {
            let Some((name, rest)) = quoted_name(tail[1..].trim_start()) else {
                continue;
            };
            second = Some(name);
            tail = rest.trim_start();
        }
        if !tail.starts_with(')') {
            continue;
        }
        let end = sql.len() - tail.len() + 1;
        spans.push(ReferenceSpan {
            start,
            end,
            name: second.unwrap_or(first).to_owned(),
            package: second.map(|_| first.to_owned()),
        });
        consumed = end;
    }
    spans
}
