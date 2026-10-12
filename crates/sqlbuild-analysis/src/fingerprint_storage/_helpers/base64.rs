//! Standard-alphabet base64 as Python's `base64.b64encode` and strict `b64decode` apply it.

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const PAD: u8 = b'=';
const SECOND_BYTE: usize = 1;
const THIRD_BYTE: usize = 2;
const PAD_START_POSITION: usize = 2;
const QUAD_LENGTH: usize = 4;

/// `base64.b64encode(value).decode("ascii")`.
pub(crate) fn encode(value: &[u8]) -> String {
    let mut encoded = String::with_capacity(value.len().div_ceil(3) * 4);
    for chunk in value.chunks(3) {
        let first = chunk[0];
        let second = chunk.get(1).copied().unwrap_or(0);
        let third = chunk.get(2).copied().unwrap_or(0);
        encoded.push(char::from(ALPHABET[usize::from(first >> 2)]));
        encoded.push(char::from(
            ALPHABET[usize::from(((first & 0x03) << 4) | (second >> 4))],
        ));
        if chunk.len() > SECOND_BYTE {
            encoded.push(char::from(
                ALPHABET[usize::from(((second & 0x0f) << 2) | (third >> 6))],
            ));
        } else {
            encoded.push(char::from(PAD));
        }
        if chunk.len() > THIRD_BYTE {
            encoded.push(char::from(ALPHABET[usize::from(third & 0x3f)]));
        } else {
            encoded.push(char::from(PAD));
        }
    }
    encoded
}

/// `binascii.a2b_base64(text, strict_mode=True)`, with CPython's error messages.
pub(crate) fn decode_strict(text: &[u8]) -> Result<Vec<u8>, String> {
    if text.first() == Some(&PAD) {
        return Err("Leading padding not allowed".to_owned());
    }
    let mut decoded: Vec<u8> = Vec::with_capacity(text.len() / 4 * 3);
    let mut quad_position: usize = 0;
    let mut left_char: u8 = 0;
    let mut pads: usize = 0;
    let mut padding_started = false;
    for (index, &character) in text.iter().enumerate() {
        if character == PAD {
            padding_started = true;
            if quad_position == 0 {
                return Err("Excess padding not allowed".to_owned());
            }
            if quad_position >= PAD_START_POSITION {
                pads += 1;
                if quad_position + pads >= QUAD_LENGTH {
                    if index + 1 < text.len() {
                        return Err("Excess data after padding".to_owned());
                    }
                    return Ok(decoded);
                }
            }
            continue;
        }
        let Some(value) = sextet(character) else {
            return Err("Only base64 data is allowed".to_owned());
        };
        if padding_started {
            return Err("Discontinuous padding not allowed".to_owned());
        }
        pads = 0;
        match quad_position {
            0 => {
                quad_position = 1;
                left_char = value;
            }
            1 => {
                quad_position = 2;
                decoded.push((left_char << 2) | (value >> 4));
                left_char = value & 0x0f;
            }
            2 => {
                quad_position = 3;
                decoded.push((left_char << 4) | (value >> 2));
                left_char = value & 0x03;
            }
            _ => {
                quad_position = 0;
                decoded.push((left_char << 6) | value);
                left_char = 0;
            }
        }
    }
    match quad_position {
        0 => Ok(decoded),
        1 => Err(format!(
            "Invalid base64-encoded string: number of data characters ({}) cannot be 1 more \
             than a multiple of 4",
            decoded.len() / 3 * 4 + 1
        )),
        _ => Err("Incorrect padding".to_owned()),
    }
}

fn sextet(character: u8) -> Option<u8> {
    match character {
        b'A'..=b'Z' => Some(character - b'A'),
        b'a'..=b'z' => Some(character - b'a' + 26),
        b'0'..=b'9' => Some(character - b'0' + 52),
        b'+' => Some(62),
        b'/' => Some(63),
        _ => None,
    }
}
