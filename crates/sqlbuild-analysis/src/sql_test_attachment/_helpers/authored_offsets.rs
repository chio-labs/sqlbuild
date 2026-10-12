//! `authored_file_offset`: an offset in a cleaned SQL-test body mapped back to the file.

use crate::sql_test_attachment::constants::TAB_SIZE;

/// One kept line of the cleaned body: its file offset, raw text and removed indent columns.
struct CleanedLine {
    start: usize,
    text: Vec<char>,
    removed: usize,
}

/// `str.expandtabs()` in code points; line breaks reset the column.
fn expand_tabs(text: &[char]) -> Vec<char> {
    let mut expanded: Vec<char> = Vec::with_capacity(text.len());
    let mut column: usize = 0;
    for &character in text {
        match character {
            '\t' => {
                let width: usize = TAB_SIZE - column % TAB_SIZE;
                expanded.extend(std::iter::repeat_n(' ', width));
                column += width;
            }
            '\n' | '\r' => {
                expanded.push(character);
                column = 0;
            }
            _ => {
                expanded.push(character);
                column += 1;
            }
        }
    }
    expanded
}

/// Whether `line.strip()` is non-empty.
fn has_content(line: &[char]) -> bool {
    line.iter().copied().any(is_not_space)
}

fn is_not_space(character: char) -> bool {
    !char::is_whitespace(character)
}

fn indent(line: &[char]) -> usize {
    line.iter()
        .take_while(|character| char::is_whitespace(**character))
        .count()
}

fn tail(line: &[char], removed: usize) -> &[char] {
    line.get(removed..).unwrap_or(&[])
}

/// `_cleaned_lines`: the kept lines when cleaning the span reproduces `authored`, else `None`.
fn cleaned_lines(
    contents: &[char],
    authored: &str,
    span: (usize, usize),
) -> Option<Vec<CleanedLine>> {
    let text: &[char] = contents.get(span.0..span.1)?;
    let raw: Vec<&[char]> = text.split(|character| *character == '\n').collect();
    let expanded: Vec<Vec<char>> = raw.iter().map(|line| expand_tabs(line)).collect();
    let margin: Option<usize> = expanded[1..]
        .iter()
        .filter(|line| has_content(line))
        .map(|line| indent(line))
        .min();
    let mut starts: Vec<usize> = Vec::with_capacity(raw.len());
    let mut cursor: usize = span.0;
    for line in &raw {
        starts.push(cursor);
        cursor += line.len() + 1;
    }
    let mut removed: Vec<usize> = vec![indent(&expanded[0])];
    removed.extend(std::iter::repeat_n(margin.unwrap_or(0), expanded.len() - 1));
    let mut kept: Vec<usize> = (0..expanded.len()).collect();
    while kept
        .last()
        .is_some_and(|&index| tail(&expanded[index], removed[index]).is_empty())
    {
        kept.pop();
    }
    while kept
        .first()
        .is_some_and(|&index| tail(&expanded[index], removed[index]).is_empty())
    {
        kept.remove(0);
    }
    let cleaned: String = kept
        .iter()
        .map(|&index| {
            tail(&expanded[index], removed[index])
                .iter()
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    if cleaned != authored {
        return None;
    }
    Some(
        kept.iter()
            .map(|&index| CleanedLine {
                start: starts[index],
                text: raw[index].to_vec(),
                removed: removed[index],
            })
            .collect(),
    )
}

/// `_authored_index`: the raw index under an expanded column.
fn authored_index(text: &[char], expanded_column: usize) -> usize {
    let mut position: usize = 0;
    let mut column: usize = 0;
    for (index, &character) in text.iter().enumerate() {
        let width: usize = if character == '\t' {
            TAB_SIZE - column % TAB_SIZE
        } else {
            1
        };
        if expanded_column < position + width {
            return index;
        }
        position += width;
        column = if character == '\r' { 0 } else { column + width };
    }
    text.len()
}

/// The file code-point offset of `body_offset` in the cleaned `authored` body, if exact.
pub(crate) fn authored_offset(
    contents: &str,
    authored: &str,
    span: Option<(usize, usize)>,
    body_offset: usize,
) -> Option<usize> {
    let contents: Vec<char> = contents.chars().collect();
    let lines: Vec<CleanedLine> = cleaned_lines(&contents, authored, span?)?;
    let body: Vec<char> = authored.chars().collect();
    let before: &[char] = body.get(..body_offset)?;
    let line_index: usize = before
        .iter()
        .filter(|character| **character == '\n')
        .count();
    let line_start: usize = before
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(0, |index| index + 1);
    let line: &CleanedLine = lines.get(line_index)?;
    Some(line.start + authored_index(&line.text, line.removed + body_offset - line_start))
}
