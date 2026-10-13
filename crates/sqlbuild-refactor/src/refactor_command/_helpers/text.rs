//! Small text helpers shared by the refactoring output.

use sqlbuild_core::cli_text::models::CliStyle;

use crate::refactor_command::constants::{EXCERPT_LIMIT, TREE_BRANCH_GLYPH, TREE_LAST_GLYPH};

/// A dim branch, or the last branch of a group.
pub(crate) fn tree_connector(style: CliStyle, last: bool) -> String {
    style.muted(if last {
        TREE_LAST_GLYPH
    } else {
        TREE_BRANCH_GLYPH
    })
}

/// Python's `str.isspace` for one character.
fn python_space(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}

/// The text on one line with runs of whitespace collapsed, cut to the excerpt limit.
pub(crate) fn excerpt(text: &str) -> String {
    let single: String = text
        .split(python_space)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    if single.chars().count() <= EXCERPT_LIMIT {
        return single;
    }
    let mut cut: String = single.chars().take(EXCERPT_LIMIT - 1).collect();
    cut.push('\u{2026}');
    cut
}

/// `text.ljust(width)` counting code points.
pub(crate) fn left_justified(text: &str, width: usize) -> String {
    let padding: usize = width.saturating_sub(text.chars().count());
    format!("{text}{}", " ".repeat(padding))
}

/// The first line of `text` as Python's `str.splitlines()` splits it.
pub(crate) fn first_line(text: &str) -> &str {
    let end: usize = text
        .char_indices()
        .find(|(_, character)| {
            matches!(
                character,
                '\n' | '\r'
                    | '\u{0b}'
                    | '\u{0c}'
                    | '\u{1c}'
                    | '\u{1d}'
                    | '\u{1e}'
                    | '\u{85}'
                    | '\u{2028}'
                    | '\u{2029}'
            )
        })
        .map_or(text.len(), |(index, _)| index);
    &text[..end]
}
