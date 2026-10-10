//! Read node properties and indicators from the source, which parser events do not carry.

/// No code character precedes the position.
const NO_CODE: usize = usize::MAX;
const TOKEN_BOUNDARIES: [char; 5] = ['[', ']', '{', '}', ','];
/// The characters PyYAML's `scan_anchor` accepts right after an anchor name.
const ANCHOR_TERMINATORS: [char; 8] = ['?', ':', ',', ']', '}', '%', '@', '`'];

/// For each char index, the end of the last code character before it, outside comments.
pub(crate) fn code_ends(chars: &[char]) -> Vec<usize> {
    let mut ends: Vec<usize> = Vec::with_capacity(chars.len() + 1);
    let mut last = NO_CODE;
    let mut in_comment = false;
    for (index, character) in chars.iter().enumerate() {
        ends.push(last);
        if *character == '\n' {
            in_comment = false;
            continue;
        }
        let line_start = index == 0 || chars[index - 1] == '\n';
        if *character == '#' && (line_start || chars[index - 1].is_whitespace()) {
            in_comment = true;
        }
        if !in_comment && !character.is_whitespace() {
            last = index + 1;
        }
    }
    ends.push(last);
    ends
}

/// The end of the last code character before `end`, skipping whitespace and comments.
fn code_end_before(code_ends: &[usize], end: usize) -> Option<usize> {
    let last = code_ends[end.min(code_ends.len() - 1)];
    (last != NO_CODE).then_some(last)
}

/// The token that ends right before `end`, skipping whitespace and comments, with its start.
fn token_before(chars: &[char], code_ends: &[usize], end: usize) -> Option<(usize, String)> {
    let token_end = code_end_before(code_ends, end)?;
    let token_start = chars[..token_end]
        .iter()
        .rposition(|character| character.is_whitespace() || TOKEN_BOUNDARIES.contains(character))
        .map_or(0, |boundary| boundary + 1);
    Some((token_start, chars[token_start..token_end].iter().collect()))
}

/// Whether a standalone `?` explicit key indicator is the last code before char index `end`.
pub(crate) fn explicit_key_before(chars: &[char], code_ends: &[usize], end: usize) -> bool {
    code_end_before(code_ends, end).is_some_and(|index| {
        let indicator = index - 1;
        let standalone = indicator == 0
            || matches!(
                chars[indicator - 1],
                ' ' | '\t' | '\n' | '\r' | '[' | '{' | ','
            );
        chars[indicator] == '?' && standalone
    })
}

/// The anchor name in `token` when PyYAML's scanner accepts the character after it.
fn anchor_token(chars: &[char], token_start: usize, token: &str) -> Option<String> {
    let name = token.strip_prefix('&')?;
    let following = chars.get(token_start + token.chars().count()).copied();
    let terminated = following.is_none_or(|character| {
        character.is_whitespace() || ANCHOR_TERMINATORS.contains(&character)
    });
    terminated.then(|| name.to_owned())
}

/// The name of the anchor property written before the node starting at char index `start`.
pub(crate) fn anchor_name(chars: &[char], code_ends: &[usize], start: usize) -> Option<String> {
    let (token_start, token) = token_before(chars, code_ends, start)?;
    if token.starts_with('&') {
        return anchor_token(chars, token_start, &token);
    }
    let (previous_start, previous) = token_before(chars, code_ends, token_start)?;
    anchor_token(chars, previous_start, &previous)
}

/// Whether PyYAML's scanner accepts `name` as an anchor: ASCII letters, digits, `-` and `_`.
pub(crate) fn is_python_anchor_name(name: &str) -> bool {
    !name.is_empty()
        && name
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
}
