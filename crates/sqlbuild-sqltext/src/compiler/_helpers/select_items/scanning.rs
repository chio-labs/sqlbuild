//! The top-level SELECT list of a model's SQL and the output name of each simple item.

const SELECT_KEYWORD: &str = "SELECT";
const UNION_KEYWORD: &str = "UNION";
const FROM_KEYWORD: &str = "FROM";
const UNION_LOWER: &str = "union";
const ESCAPE: char = '\\';
const QUOTES: [char; 2] = ['\'', '"'];
const SCAN_SPECIAL: [char; 9] = ['\'', '"', '`', '(', ')', 's', 'S', 'f', 'F'];
const UNION_INITIALS: [char; 2] = ['u', 'U'];
const IDENTIFIER_SEPARATOR: char = '_';
const DOUBLE_QUOTE: char = '"';
const CLOSE_PAREN: char = ')';
/// Letters `[A-Za-z]` matches under `re.IGNORECASE` besides the ASCII ones.
const IGNORECASE_EXTRA_LETTERS: [char; 4] = ['\u{130}', '\u{131}', '\u{17f}', '\u{212a}'];
const IGNORECASE_S: [char; 3] = ['s', 'S', '\u{17f}'];
const AS_LENGTH: usize = 2;
/// `end_column` is one past the last character, which is itself one-based.
const END_COLUMN_OFFSET: usize = 2;

fn is_special(character: char) -> bool {
    SCAN_SPECIAL.contains(&character) || UNION_INITIALS.contains(&character)
}

/// `_keyword_at`: `keyword` at `index`, not inside a longer word.
fn keyword_at(sql: &[char], keyword: &str, index: usize) -> bool {
    let end = index + keyword.chars().count();
    let slice: String = sql[index..end.min(sql.len())].iter().collect();
    if str::to_uppercase(&slice) != keyword {
        return false;
    }
    let word = |character: Option<&char>| {
        character.is_some_and(|character| {
            char::is_alphanumeric(*character) || *character == IDENTIFIER_SEPARATOR
        })
    };
    let before = index.checked_sub(1).and_then(|position| sql.get(position));
    !word(before) && !word(sql.get(end))
}

fn has_union_candidate(sql: &[char]) -> bool {
    let lowered: String = sql.iter().collect::<String>().to_lowercase();
    lowered.contains(UNION_LOWER)
}

/// The scan state of `_top_level_select_list_bounds`.
#[derive(Clone, Copy)]
struct ListScan {
    depth: usize,
    start: Option<usize>,
    end: Option<usize>,
}

/// What one character does to the scan: advance by a count, or finish with a result.
enum Step {
    Advance(usize),
    Jump(usize),
    Finish(Option<(usize, usize)>),
}

fn top_level_step(sql: &[char], index: usize, scan: ListScan, unions: bool) -> (Step, ListScan) {
    let mut scan = scan;
    let character = sql[index];
    if character == '(' {
        scan.depth += 1;
        return (Step::Advance(1), scan);
    }
    if character == CLOSE_PAREN {
        scan.depth = scan.depth.saturating_sub(1);
        return (Step::Advance(1), scan);
    }
    if scan.depth != 0 {
        return (Step::Advance(1), scan);
    }
    let upper = character.to_ascii_uppercase();
    let Some(start) = scan.start else {
        if upper == 'S' && keyword_at(sql, SELECT_KEYWORD, index) {
            let start = index + SELECT_KEYWORD.len();
            scan.start = Some(start);
            return (Step::Jump(start), scan);
        }
        return (Step::Advance(1), scan);
    };
    if upper == 'U' && keyword_at(sql, UNION_KEYWORD, index) {
        return (Step::Finish(None), scan);
    }
    if scan.end.is_none() && upper == 'F' && keyword_at(sql, FROM_KEYWORD, index) {
        scan.end = Some(index);
        if !unions {
            return (Step::Finish(Some((start, index))), scan);
        }
    }
    (Step::Advance(1), scan)
}

/// `_top_level_select_list_bounds`: the SELECT list of the first top-level SELECT.
pub(crate) fn select_list_bounds(sql: &[char]) -> Option<(usize, usize)> {
    let unions = has_union_candidate(sql);
    let mut scan = ListScan {
        depth: 0,
        start: None,
        end: None,
    };
    let mut quote: Option<char> = None;
    let mut index = 0;
    while index < sql.len() {
        if let Some(open) = quote {
            if sql[index] == ESCAPE {
                index += 2;
                continue;
            }
            if sql[index] == open {
                quote = None;
            }
            index += 1;
            continue;
        }
        let Some(offset) = sql[index..]
            .iter()
            .position(|character| is_special(*character))
        else {
            break;
        };
        index += offset;
        if QUOTES.contains(&sql[index]) {
            quote = Some(sql[index]);
            index += 1;
            continue;
        }
        let (step, next) = top_level_step(sql, index, scan, unions);
        scan = next;
        match step {
            Step::Advance(count) => index += count,
            Step::Jump(position) => index = position,
            Step::Finish(bounds) => return bounds,
        }
    }
    scan.start
        .map(|start| (start, scan.end.unwrap_or(sql.len())))
}

/// `_split_top_level_select_items`: item ranges split at top-level commas.
pub(crate) fn split_select_items(sql: &[char], start: usize, end: usize) -> Vec<(usize, usize)> {
    let mut items: Vec<(usize, usize)> = Vec::new();
    let mut depth: usize = 0;
    let mut item_start = start;
    let mut quote: Option<char> = None;
    let mut index = start;
    while index < end {
        let character = sql[index];
        if let Some(open) = quote {
            if character == ESCAPE {
                index += 2;
                continue;
            }
            if character == open {
                quote = None;
            }
            index += 1;
            continue;
        }
        if QUOTES.contains(&character) {
            quote = Some(character);
        } else if character == '(' {
            depth += 1;
        } else if character == CLOSE_PAREN {
            depth = depth.saturating_sub(1);
        } else if character == ',' && depth == 0 {
            items.push((item_start, index));
            item_start = index + 1;
        }
        index += 1;
    }
    items.push((item_start, end));
    items
}

fn is_identifier_start(character: char, ignore_case: bool) -> bool {
    character.is_ascii_alphabetic()
        || character == IDENTIFIER_SEPARATOR
        || (ignore_case && IGNORECASE_EXTRA_LETTERS.contains(&character))
}

fn is_identifier_part(character: char, ignore_case: bool) -> bool {
    is_identifier_start(character, ignore_case) || character.is_ascii_digit()
}

fn trim_end(text: &[char]) -> &[char] {
    let end = text
        .iter()
        .rposition(|character| !char::is_whitespace(*character))
        .map_or(0, |position| position + 1);
    &text[..end]
}

fn trim_start(text: &[char]) -> &[char] {
    let start = text
        .iter()
        .position(|character| !char::is_whitespace(*character))
        .unwrap_or(text.len());
    &text[start..]
}

/// The start of an `IDENT|"[^"]+"` name ending `text`, or `None`.
fn trailing_name_start(text: &[char], ignore_case: bool) -> Option<usize> {
    if text.last() == Some(&DOUBLE_QUOTE) {
        let open = text[..text.len() - 1]
            .iter()
            .rposition(|character| *character == DOUBLE_QUOTE)?;
        return (open + 2 < text.len()).then_some(open);
    }
    let start = text
        .iter()
        .rposition(|character| !is_identifier_part(*character, ignore_case))
        .map_or(0, |position| position + 1);
    (start < text.len() && is_identifier_start(text[start], ignore_case)).then_some(start)
}

fn is_full_name(text: &[char]) -> bool {
    match text {
        [DOUBLE_QUOTE, inner @ .., DOUBLE_QUOTE] => {
            !inner.is_empty() && !inner.contains(&DOUBLE_QUOTE)
        }
        [first, rest @ ..] => {
            is_identifier_start(*first, false)
                && rest
                    .iter()
                    .all(|character| is_identifier_part(*character, false))
        }
        [] => false,
    }
}

/// `\s+AS\s+NAME\s*\Z` under `re.IGNORECASE`.
fn explicit_alias(text: &[char]) -> Option<&[char]> {
    let start = trailing_name_start(text, true)?;
    let before = &text[..start];
    let spaced = trim_end(before);
    if spaced.len() == before.len() || spaced.len() < AS_LENGTH {
        return None;
    }
    let keyword = &spaced[spaced.len() - AS_LENGTH..];
    let is_as = matches!(keyword[0], 'a' | 'A') && IGNORECASE_S.contains(&keyword[1]);
    let preceding = &spaced[..spaced.len() - AS_LENGTH];
    (is_as
        && preceding
            .last()
            .is_some_and(|character| char::is_whitespace(*character)))
    .then_some(&text[start..])
}

/// `\s*(?:(?:IDENT|"[^"]+")\.)?NAME\s*\Z` from the start.
fn bare_reference(text: &[char]) -> Option<&[char]> {
    let trimmed = trim_start(text);
    if let Some(dot) = qualifier_end(trimmed)
        && is_full_name(&trimmed[dot + 1..])
    {
        return Some(&trimmed[dot + 1..]);
    }
    is_full_name(trimmed).then_some(trimmed)
}

/// The index of the `.` after a leading `IDENT` or `"[^"]+"` qualifier.
fn qualifier_end(text: &[char]) -> Option<usize> {
    let end = if text.first() == Some(&DOUBLE_QUOTE) {
        let close = text[1..]
            .iter()
            .position(|character| *character == DOUBLE_QUOTE)?
            + 1;
        (close > 1).then_some(close + 1)?
    } else {
        let length = text
            .iter()
            .position(|character| !is_identifier_part(*character, false))
            .unwrap_or(text.len());
        (length > 0 && is_identifier_start(text[0], false)).then_some(length)?
    };
    (text.get(end) == Some(&'.')).then_some(end)
}

/// `\)\s+NAME\s*\Z`.
fn implicit_alias(text: &[char]) -> Option<&[char]> {
    let start = trailing_name_start(text, false)?;
    let before = &text[..start];
    let spaced = trim_end(before);
    (spaced.len() < before.len() && spaced.last() == Some(&CLOSE_PAREN)).then_some(&text[start..])
}

/// `_select_item_output_name`: the output name of a simple SELECT item, quotes stripped.
pub(crate) fn select_item_output_name(item: &[char], implicit_aliases: bool) -> Option<String> {
    let text = trim_end(item);
    let name = explicit_alias(text)
        .or_else(|| bare_reference_with_trailing(item))
        .or_else(|| implicit_aliases.then(|| implicit_alias(text)).flatten())?;
    let stripped: String = name.iter().collect();
    Some(stripped.trim_matches(DOUBLE_QUOTE).to_owned())
}

fn bare_reference_with_trailing(item: &[char]) -> Option<&[char]> {
    bare_reference(trim_end(item))
}

/// `entries[name] = value`: a repeated name keeps its first position and takes the new value.
pub(crate) fn insert_named<T>(
    entries: Vec<(String, T)>,
    name: String,
    value: T,
) -> Vec<(String, T)> {
    let mut updated = entries;
    match updated.iter_mut().find(|(existing, _)| *existing == name) {
        Some(entry) => entry.1 = value,
        None => updated.push((name, value)),
    }
    updated
}

/// The code-point offset where each line of `text` starts.
pub(crate) fn line_starts(text: &[char]) -> Vec<usize> {
    std::iter::once(0)
        .chain(
            text.iter()
                .enumerate()
                .filter(|(_, character)| **character == '\n')
                .map(|(index, _)| index + 1),
        )
        .collect()
}

/// `_location_for_absolute_span`: one-based lines and columns of `[start, end)`.
pub(crate) fn span_location(
    starts: &[usize],
    start: usize,
    end: usize,
) -> crate::compiler::models::TextLocation {
    let end = end.max(start);
    let end_position = start.max(end.saturating_sub(1));
    let line_index = starts.partition_point(|line_start| *line_start <= start) - 1;
    let end_line_index = starts.partition_point(|line_start| *line_start <= end_position) - 1;
    crate::compiler::models::TextLocation {
        line: line_index + 1,
        column: start - starts[line_index] + 1,
        end_line: end_line_index + 1,
        end_column: end_position - starts[end_line_index] + END_COLUMN_OFFSET,
    }
}

/// The trimmed code-point span of a SELECT item, or `None` when it is blank.
pub(crate) fn trimmed_item(sql: &[char], (start, end): (usize, usize)) -> Option<(usize, usize)> {
    let item = &sql[start..end];
    let leading = item
        .iter()
        .position(|character| !char::is_whitespace(*character))
        .unwrap_or(item.len());
    let trailing = item
        .iter()
        .rposition(|character| !char::is_whitespace(*character))
        .map_or(0, |position| position + 1);
    (leading < trailing).then_some((start + leading, start + trailing))
}
