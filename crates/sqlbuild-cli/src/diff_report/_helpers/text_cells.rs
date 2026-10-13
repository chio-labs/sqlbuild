//! Terminal cell widths and Rich's word wrapping of one line of text.

use sqlbuild_core::text::main::cell_len::cell_len;
use sqlbuild_core::text::main::char_cells::char_cells;

/// The longest prefix of `text` that fits `width` cells, padded with spaces to exactly `width`.
pub(crate) fn set_cell_size(text: &str, width: usize) -> String {
    let mut result: String = String::new();
    let mut used: usize = 0;
    for character in text.chars() {
        let cells: usize = char_cells(character);
        if used + cells > width {
            break;
        }
        used += cells;
        result.push(character);
    }
    result.push_str(&" ".repeat(width - used));
    result
}

/// Whitespace-then-word-then-whitespace pieces, as `\s*\S+\s*` matches them.
fn words(characters: &[char]) -> Vec<(usize, usize)> {
    let mut pieces: Vec<(usize, usize)> = Vec::new();
    let mut position: usize = 0;
    while position < characters.len() {
        let start: usize = position;
        let mut cursor: usize = position;
        while cursor < characters.len() && characters[cursor].is_whitespace() {
            cursor += 1;
        }
        if cursor == characters.len() {
            break;
        }
        while cursor < characters.len() && !characters[cursor].is_whitespace() {
            cursor += 1;
        }
        while cursor < characters.len() && characters[cursor].is_whitespace() {
            cursor += 1;
        }
        pieces.push((start, cursor));
        position = cursor;
    }
    pieces
}

fn text_cells(characters: &[char]) -> usize {
    characters.iter().copied().map(char_cells).sum()
}

fn trimmed_end(characters: &[char]) -> &[char] {
    let mut end: usize = characters.len();
    while end > 0 && characters[end - 1].is_whitespace() {
        end -= 1;
    }
    &characters[..end]
}

/// `chop_cells`: consecutive pieces of at most `width` cells.
fn chop_cells(characters: &[char], width: usize) -> Vec<Vec<char>> {
    let mut lines: Vec<Vec<char>> = Vec::new();
    let mut line: Vec<char> = Vec::new();
    let mut size: usize = 0;
    for character in characters {
        let cells: usize = char_cells(*character);
        if size + cells > width && !line.is_empty() {
            lines.push(std::mem::take(&mut line));
            size = 0;
        }
        size += cells;
        line.push(*character);
    }
    if !line.is_empty() {
        lines.push(line);
    }
    lines
}

/// Rich's `divide_line`: character offsets where a line breaks to fit `width` cells.
fn divide_line(characters: &[char], width: usize, fold: bool) -> Vec<usize> {
    let mut breaks: Vec<usize> = Vec::new();
    let mut offset: usize = 0;
    for (word_start, word_end) in words(characters) {
        let mut start: usize = word_start;
        let word: &[char] = &characters[word_start..word_end];
        let word_length: usize = text_cells(trimmed_end(word));
        if width.saturating_sub(offset) >= word_length && offset <= width {
            offset += text_cells(word);
        } else if word_length > width {
            if fold {
                let folded: Vec<Vec<char>> = chop_cells(word, width);
                let count: usize = folded.len();
                for (index, piece) in folded.iter().enumerate() {
                    if start > 0 {
                        breaks.push(start);
                    }
                    if index + 1 == count {
                        offset = text_cells(piece);
                    } else {
                        start += piece.len();
                    }
                }
            } else {
                if start > 0 {
                    breaks.push(start);
                }
                offset = text_cells(word);
            }
        } else if offset > 0 && start > 0 {
            breaks.push(start);
            offset = text_cells(word);
        }
    }
    breaks
}

/// One source line wrapped to `width` cells like `Text.wrap` without justification.
pub(crate) fn wrap_line(line: &str, width: usize, fold: bool) -> Vec<String> {
    let characters: Vec<char> = line.chars().collect();
    let mut pieces: Vec<String> = Vec::new();
    let mut previous: usize = 0;
    let mut breaks: Vec<usize> = divide_line(&characters, width, fold);
    breaks.push(characters.len());
    for offset in breaks {
        let mut piece: Vec<char> = characters[previous..offset].to_vec();
        previous = offset;
        if piece.len() > width {
            let excess: usize = piece.len() - width;
            let trailing: usize = piece.len() - trimmed_end(&piece).len();
            piece.truncate(piece.len() - trailing.min(excess));
        }
        let text: String = piece.into_iter().collect();
        pieces.push(if cell_len(&text) > width {
            if fold {
                set_cell_size(&text, width)
            } else {
                set_cell_size(&text, width.saturating_sub(1)) + "…"
            }
        } else {
            text
        });
    }
    pieces
}
