//! Authored locations as Python computes them: code-point columns over `\n`-separated lines.

use crate::models::LineColumnSpan;

/// Python's `header_column_locations` for the native tokenizer's column-key offsets.
pub(crate) fn header_column_locations(
    contents: &str,
    (header_start, header_end): (usize, usize),
    offsets: &[(String, usize, usize)],
) -> Vec<(String, LineColumnSpan)> {
    if offsets.is_empty() {
        return Vec::new();
    }
    let before_header = &contents[..header_start];
    let header_line = before_header.matches('\n').count() + 1;
    let line_start = before_header.rfind('\n').map_or(0, |index| index + 1);
    let header_column = before_header[line_start..].chars().count() + 1;
    let header: Vec<char> = contents[header_start..header_end].chars().collect();
    relative_locations(&header, offsets)
        .into_iter()
        .map(|(name, relative_line, relative_column, length)| {
            let line = header_line + relative_line - 1;
            let column = relative_column
                + if relative_line == 1 {
                    header_column - 1
                } else {
                    0
                };
            (
                name,
                LineColumnSpan {
                    line,
                    column,
                    end_line: line,
                    end_column: column + length,
                },
            )
        })
        .collect()
}

/// Python's `_header_column_relative_locations`, including its forward-only cursor.
fn relative_locations(
    header: &[char],
    offsets: &[(String, usize, usize)],
) -> Vec<(String, usize, usize, usize)> {
    let mut locations = Vec::with_capacity(offsets.len());
    let (mut line, mut column, mut cursor) = (1, 1, 0);
    for (name, position, length) in offsets {
        while cursor < *position {
            let newline = header[cursor..*position.min(&header.len())]
                .iter()
                .position(|character| *character == '\n');
            match newline {
                None => {
                    column += position - cursor;
                    cursor = *position;
                }
                Some(offset) => {
                    line += 1;
                    column = 1;
                    cursor += offset + 1;
                }
            }
        }
        locations.push((name.clone(), line, column, *length));
    }
    locations
}

/// Code-point offsets where each line starts.
pub(crate) fn line_starts(contents: &[char]) -> Vec<usize> {
    let mut starts = vec![0];
    starts.extend(
        contents
            .iter()
            .enumerate()
            .filter(|(_, character)| **character == '\n')
            .map(|(index, _)| index + 1),
    );
    starts
}

/// Python's `_location_for_absolute_span` over code-point offsets.
pub(crate) fn absolute_span(start: usize, end: usize, starts: &[usize]) -> LineColumnSpan {
    let end = end.max(start);
    let end_position = start.max(end.saturating_sub(1));
    let line_index = starts.partition_point(|line_start| *line_start <= start) - 1;
    let end_line_index = starts.partition_point(|line_start| *line_start <= end_position) - 1;
    LineColumnSpan {
        line: line_index + 1,
        column: start - starts[line_index] + 1,
        end_line: end_line_index + 1,
        end_column: end_position - starts[end_line_index] + 2,
    }
}
