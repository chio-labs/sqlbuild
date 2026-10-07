//! Conversions between UTF-8 byte offsets and Python code-point offsets of one text.

/// Return the code-point offset of each ascending byte offset in `byte_offsets`.
pub(crate) fn char_offsets(text: &str, byte_offsets: &[usize]) -> Vec<usize> {
    if text.is_ascii() {
        return byte_offsets.to_vec();
    }
    let mut converted = Vec::with_capacity(byte_offsets.len());
    let mut byte = 0;
    let mut chars = 0;
    for offset in byte_offsets {
        chars += text[byte..*offset].chars().count();
        byte = *offset;
        converted.push(chars);
    }
    converted
}

/// Return the byte offset of each ascending code-point offset, or `None` past the end of `text`.
pub(crate) fn byte_offsets(text: &str, char_offsets: &[usize]) -> Option<Vec<usize>> {
    if text.is_ascii() {
        return char_offsets
            .iter()
            .all(|offset| *offset <= text.len())
            .then(|| char_offsets.to_vec());
    }
    let mut converted = Vec::with_capacity(char_offsets.len());
    let mut indices = text
        .char_indices()
        .map(|(byte, _)| byte)
        .chain([text.len()]);
    let mut position = 0;
    let mut current = indices.next()?;
    for offset in char_offsets {
        if *offset < position {
            return None;
        }
        while position < *offset {
            current = indices.next()?;
            position += 1;
        }
        converted.push(current);
    }
    Some(converted)
}
