//! Section entry and detail rows connected into trees.

use crate::cli_text::_helpers::bounded_sections::strip_ansi;
use crate::cli_text::_helpers::layout::tree_connector;
use crate::cli_text::constants::{
    ENTRY_ROW_PREFIX, LEAF_KEY_SEPARATOR, LEAF_ROW_PREFIX, NESTED_ROW_PREFIX, STYLE_ESCAPE_END,
    STYLE_ESCAPE_START, TREE_CONTINUATION_GLYPH, TREE_EXEMPT_CHARS,
};
use crate::cli_text::models::{CliStyle, RowKind};

fn classify(line: &str) -> RowKind {
    let plain: String = strip_ansi(line);
    if plain.trim().is_empty() || !plain.starts_with(ENTRY_ROW_PREFIX) {
        return RowKind::Other;
    }
    if plain.starts_with(NESTED_ROW_PREFIX) {
        return RowKind::Nested;
    }
    let (prefix, kind) = if plain.starts_with(LEAF_ROW_PREFIX) {
        (LEAF_ROW_PREFIX, RowKind::Leaf)
    } else {
        (ENTRY_ROW_PREFIX, RowKind::Entry)
    };
    if plain[prefix.len()..]
        .chars()
        .next()
        .is_some_and(|first| TREE_EXEMPT_CHARS.contains(&first))
    {
        return RowKind::Other;
    }
    kind
}

/// Whether the row is the final one of its kind within its block.
fn is_last(kinds: &[RowKind], index: usize, row_kind: RowKind) -> bool {
    for kind in &kinds[index + 1..] {
        match (row_kind, kind) {
            (_, RowKind::Other) | (RowKind::Leaf, RowKind::Entry) => return true,
            (RowKind::Entry, RowKind::Entry) | (RowKind::Leaf, RowKind::Leaf) => return false,
            _ => {}
        }
    }
    true
}

/// A nested row whose leaf indentation becomes a non-last entry's bar, keeping style escapes.
fn continued(line: String, continuation: Option<&str>) -> String {
    let Some(continuation) = continuation else {
        return line;
    };
    let mut kept: String = String::with_capacity(line.len());
    let mut removed: usize = 0;
    let mut characters = line.chars().peekable();
    while removed < LEAF_ROW_PREFIX.len() {
        match characters.next() {
            Some(STYLE_ESCAPE_START) => {
                kept.push(STYLE_ESCAPE_START);
                for character in characters.by_ref() {
                    kept.push(character);
                    if character == STYLE_ESCAPE_END {
                        break;
                    }
                }
            }
            Some(' ') => removed += 1,
            _ => return line,
        }
    }
    kept.extend(characters);
    format!("{continuation}{kept}")
}

/// `_treeify_plan_lines`: entry rows and their detail rows drawn with tree connectors.
pub(crate) fn treeify(lines: Vec<String>) -> Vec<String> {
    let style: CliStyle = CliStyle { use_color: true };
    let kinds: Vec<RowKind> = lines.iter().map(|line| classify(line)).collect();
    let mut out: Vec<String> = Vec::with_capacity(lines.len());
    let mut bar: Option<String> = None;
    for (index, line) in lines.into_iter().enumerate() {
        match kinds[index] {
            RowKind::Entry => {
                let last: bool = is_last(&kinds, index, RowKind::Entry);
                bar = (!last).then(|| style.muted(TREE_CONTINUATION_GLYPH));
                let connector: String = tree_connector(style, last);
                out.push(format!("{connector} {}", &line[ENTRY_ROW_PREFIX.len()..]));
            }
            RowKind::Leaf => {
                let continuation: &str = bar.as_deref().unwrap_or(LEAF_ROW_PREFIX);
                let connector: String =
                    tree_connector(style, is_last(&kinds, index, RowKind::Leaf));
                let content: String = match line.strip_prefix(LEAF_ROW_PREFIX) {
                    Some(content) => content.to_owned(),
                    None => strip_ansi(&line)[LEAF_ROW_PREFIX.len()..].to_owned(),
                };
                if let Some((key, value)) = content.split_once(LEAF_KEY_SEPARATOR) {
                    out.push(format!(
                        "{continuation}{connector} {}  {value}",
                        style.muted(key)
                    ));
                } else if content.ends_with(':') {
                    out.push(format!(
                        "{continuation}{connector} {}",
                        style.muted(&content)
                    ));
                } else {
                    out.push(format!("{continuation}{connector} {content}"));
                }
            }
            RowKind::Nested => out.push(continued(line, bar.as_deref())),
            RowKind::Other => {
                bar = None;
                out.push(line);
            }
        }
    }
    out
}
