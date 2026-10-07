//! The code-point scanning helpers Python's audit parser uses: comments, quotes and keywords.

use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;

const SQL_QUOTES: [char; 3] = ['\'', '"', '`'];

/// Audit text as code points, with the Python semantics its keyword checks use.
pub(crate) struct AuditText<'a> {
    pub(crate) chars: &'a [char],
    pub(crate) python: PythonText,
}

impl AuditText<'_> {
    pub(crate) fn len(&self) -> usize {
        self.chars.len()
    }

    fn starts_with(&self, index: usize, prefix: &[char]) -> bool {
        self.chars
            .get(index..)
            .is_some_and(|rest| rest.starts_with(prefix))
    }

    /// `text.find(needle, start)`.
    fn find(&self, needle: &[char], start: usize) -> Option<usize> {
        (start..self.len()).find(|index| self.starts_with(*index, needle))
    }

    /// `_code_characters`: positions outside quotes and comments, from `start`.
    pub(crate) fn code_positions(&self, start: usize) -> Vec<usize> {
        let mut positions: Vec<usize> = Vec::new();
        let length: usize = self.len();
        let mut index: usize = start;
        while index < length {
            let character: char = self.chars[index];
            if self.starts_with(index, &['-', '-']) {
                index = self
                    .find(&['\n'], index + 2)
                    .map_or(length, |newline| newline + 1);
                continue;
            }
            if self.starts_with(index, &['/', '*']) {
                index = self
                    .find(&['*', '/'], index + 2)
                    .map_or(length, |close| close + 2);
                continue;
            }
            if SQL_QUOTES.contains(&character) {
                index += 1;
                while index < length {
                    if self.chars[index] == character {
                        if self.chars.get(index + 1) == Some(&character) {
                            index += 2;
                            continue;
                        }
                        index += 1;
                        break;
                    }
                    index += if self.chars[index] == '\\' { 2 } else { 1 };
                }
                continue;
            }
            positions.push(index);
            index += 1;
        }
        positions
    }

    /// `_skip_space_and_comments`.
    pub(crate) fn skip_space_and_comments(&self, start: usize) -> usize {
        let length: usize = self.len();
        let mut position: usize = start;
        while position < length {
            if is_python_space(self.chars[position]) {
                position += 1;
            } else if self.starts_with(position, &['-', '-']) {
                position = self
                    .find(&['\n'], position + 2)
                    .map_or(length, |newline| newline + 1);
            } else if self.starts_with(position, &['/', '*']) {
                position = self
                    .find(&['*', '/'], position + 2)
                    .map_or(length, |close| close + 2);
            } else {
                break;
            }
        }
        position
    }

    /// `_keyword_at`: `text[position:end].upper() == keyword` between non-word characters.
    pub(crate) fn keyword_at(&self, keyword: &str, position: usize) -> bool {
        let keyword: Vec<char> = keyword.chars().collect();
        let end: usize = position + keyword.len();
        let Some(slice) = self.chars.get(position..end.min(self.len())) else {
            return false;
        };
        if slice.len() != keyword.len()
            || !slice
                .iter()
                .zip(&keyword)
                .all(|(character, expected)| upper_is(*character, *expected))
        {
            return false;
        }
        let word = |index: Option<usize>| {
            index
                .and_then(|index| self.chars.get(index))
                .is_some_and(|character| {
                    *character == '_' || is_python_alnum(self.python, *character)
                })
        };
        !word(position.checked_sub(1)) && !word(Some(end))
    }

    /// `_find_top_level_keywords`: keyword positions at depth 0 followed by `(`.
    pub(crate) fn top_level_keywords(&self, keyword: &str) -> Vec<usize> {
        let first: char = keyword.chars().next().unwrap_or_default();
        let mut depth: usize = 0;
        let mut found: Vec<usize> = Vec::new();
        for index in self.code_positions(0) {
            let character: char = self.chars[index];
            if character == '(' {
                depth += 1;
            } else if character == ')' {
                depth = depth.saturating_sub(1);
            } else if depth == 0 && upper_is(character, first) && self.keyword_at(keyword, index) {
                let after: usize = self.skip_space_and_comments(index + keyword.chars().count());
                if self.chars.get(after) == Some(&'(') {
                    found.push(index);
                }
            }
        }
        found
    }

    /// `_top_level_semicolons`.
    pub(crate) fn top_level_semicolons(&self) -> Vec<usize> {
        let mut depth: usize = 0;
        let mut found: Vec<usize> = Vec::new();
        for index in self.code_positions(0) {
            match self.chars[index] {
                '(' => depth += 1,
                ')' => depth = depth.saturating_sub(1),
                ';' if depth == 0 => found.push(index),
                _ => {}
            }
        }
        found
    }

    /// `_find_matching_parenthesis`: the closing parenthesis of the one at `open_index`.
    pub(crate) fn matching_parenthesis(&self, open_index: usize) -> Option<usize> {
        let mut depth: usize = 1;
        for index in self.code_positions(open_index + 1) {
            match self.chars[index] {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        return Some(index);
                    }
                }
                _ => {}
            }
        }
        None
    }
}

/// Whether Python's `character.upper()` is exactly the ASCII uppercase letter `expected`.
fn upper_is(character: char, expected: char) -> bool {
    match character {
        '\u{131}' => expected == 'I',
        '\u{17f}' => expected == 'S',
        _ => character.to_ascii_uppercase() == expected && character.is_ascii(),
    }
}

/// Code points of `text`.
pub(crate) fn chars(text: &str) -> Vec<char> {
    text.chars().collect()
}

/// A string from code points.
pub(crate) fn text(chars: &[char]) -> String {
    chars.iter().collect()
}
