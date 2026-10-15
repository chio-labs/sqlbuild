//! URL-safe base64 as Python's `base64.urlsafe_b64encode` and `urlsafe_b64decode` apply it.

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const PAD: u8 = b'=';
const SEXTET_BITS: u32 = 6;
const BYTE_BITS: u32 = 8;
const QUAD_LENGTH: usize = 4;
const MAX_PADDING: usize = 2;
const TRIPLE_LENGTH: usize = 3;
const LOW_SEXTET: u32 = 0x3f;
const LOW_BYTE: u32 = 0xff;

/// `base64.urlsafe_b64encode(value).decode()`.
pub(crate) fn encode(value: &[u8]) -> String {
    let mut encoded = String::with_capacity(value.len().div_ceil(TRIPLE_LENGTH) * QUAD_LENGTH);
    for chunk in value.chunks(TRIPLE_LENGTH) {
        let bits: u32 = chunk
            .iter()
            .chain(std::iter::repeat_n(&0, TRIPLE_LENGTH - chunk.len()))
            .fold(0, |bits, byte| (bits << BYTE_BITS) | u32::from(*byte));
        for position in 0..QUAD_LENGTH {
            if position > chunk.len() {
                encoded.push(char::from(PAD));
                continue;
            }
            let shift: u32 = SEXTET_BITS * (3 - position as u32);
            encoded.push(char::from(
                ALPHABET[((bits >> shift) & LOW_SEXTET) as usize],
            ));
        }
    }
    encoded
}

/// Decoded bytes of padded URL-safe or standard base64, or `None` when malformed.
pub(crate) fn decode(text: &str) -> Option<Vec<u8>> {
    let bytes: &[u8] = text.as_bytes();
    if !bytes.len().is_multiple_of(QUAD_LENGTH) {
        return None;
    }
    let mut decoded: Vec<u8> = Vec::with_capacity(bytes.len() / QUAD_LENGTH * TRIPLE_LENGTH);
    let quad_count: usize = bytes.len() / QUAD_LENGTH;
    for (index, quad) in bytes.chunks(QUAD_LENGTH).enumerate() {
        let padding: usize = quad.iter().rev().take_while(|byte| **byte == PAD).count();
        if padding > MAX_PADDING || (padding > 0 && index + 1 != quad_count) {
            return None;
        }
        let mut bits: u32 = 0;
        for byte in &quad[..QUAD_LENGTH - padding] {
            bits = (bits << SEXTET_BITS) | u32::from(sextet(*byte)?);
        }
        bits <<= SEXTET_BITS * padding as u32;
        for position in 0..(TRIPLE_LENGTH - padding) {
            let shift: u32 = BYTE_BITS * (2 - position as u32);
            decoded.push(((bits >> shift) & LOW_BYTE) as u8);
        }
    }
    Some(decoded)
}

fn sextet(character: u8) -> Option<u8> {
    match character {
        b'A'..=b'Z' => Some(character - b'A'),
        b'a'..=b'z' => Some(character - b'a' + 26),
        b'0'..=b'9' => Some(character - b'0' + 52),
        b'-' | b'+' => Some(62),
        b'_' | b'/' => Some(63),
        _ => None,
    }
}
