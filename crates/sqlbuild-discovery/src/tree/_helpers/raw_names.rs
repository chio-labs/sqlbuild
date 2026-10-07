//! Path segments for names that are not valid UTF-8: unique, and ordered as Python orders them.

use std::borrow::Cow;
use std::ffi::OsStr;

/// Brackets a raw name's hex after its lossy text; no file name can contain it.
const RAW_MARKER: char = '\0';
const PATH_SEPARATOR: u32 = '/' as u32;
const SURROGATE_ESCAPE_BASE: u32 = 0xDC00;
const ESCAPED_BYTE_FIRST: u32 = 0xDC80;
const ESCAPED_BYTE_LAST: u32 = 0xDCFF;
const BYTE_HEX_DIGITS: usize = 2;
const WIDE_HEX_DIGITS: usize = 4;
const HEX_RADIX: u32 = 16;

/// The segment naming a listed entry whose name is not valid UTF-8: lossy text, then raw hex.
pub(crate) fn raw_segment(lossy: &str, raw: &OsStr) -> String {
    format!("{lossy}{RAW_MARKER}{}{RAW_MARKER}", raw_hex(raw))
}

/// Whether a relative path holds a segment whose name is not valid UTF-8.
pub(crate) fn has_raw_segment(text: &str) -> bool {
    text.contains(RAW_MARKER)
}

/// Text as a user sees it: each raw name with its invalid bytes as `\\xNN` escapes.
pub(crate) fn display_text(text: &str) -> Cow<'_, str> {
    if !has_raw_segment(text) {
        return Cow::Borrowed(text);
    }
    let parts: Vec<&str> = text.split(RAW_MARKER).collect();
    let mut shown = String::new();
    for (index, part) in parts.iter().enumerate() {
        if index % 2 == 1 {
            let points: Vec<u32> = hex_code_points(part);
            shown.push_str(&escaped_text(&points));
        } else if index + 1 < parts.len() {
            let lossy: String = lossy_text(parts[index + 1]);
            shown.push_str(part.strip_suffix(lossy.as_str()).unwrap_or(part));
        } else {
            shown.push_str(part);
        }
    }
    Cow::Owned(shown)
}

/// Python's code points for a raw name's hex, decoded for this platform.
fn hex_code_points(hex: &str) -> Vec<u32> {
    if cfg!(windows) {
        escaped_wide(&hex_units(hex, WIDE_HEX_DIGITS))
    } else {
        escaped_bytes(&hex_units(hex, BYTE_HEX_DIGITS))
    }
}

/// The lossy name listing gave for a raw name's hex (`to_string_lossy`).
fn lossy_text(hex: &str) -> String {
    if cfg!(windows) {
        let units: Vec<u16> = hex_units(hex, WIDE_HEX_DIGITS)
            .into_iter()
            .map(|unit| u16::try_from(unit).unwrap_or(u16::MAX))
            .collect();
        String::from_utf16_lossy(&units)
    } else {
        let bytes: Vec<u8> = hex_units(hex, BYTE_HEX_DIGITS)
            .into_iter()
            .map(|byte| u8::try_from(byte).unwrap_or(u8::MAX))
            .collect();
        String::from_utf8_lossy(&bytes).into_owned()
    }
}

/// Code points as text, each escaped byte as `\xNN` and any other surrogate as `\uXXXX`.
pub(crate) fn escaped_text(points: &[u32]) -> String {
    points
        .iter()
        .map(|point| match char::from_u32(*point) {
            Some(character) => character.to_string(),
            None if (ESCAPED_BYTE_FIRST..=ESCAPED_BYTE_LAST).contains(point) => {
                format!("\\x{:02x}", point - SURROGATE_ESCAPE_BASE)
            }
            None => format!("\\u{point:04x}"),
        })
        .collect()
}

/// The code points of Python's `str` for one segment, with raw names surrogate-escaped.
pub(crate) fn segment_code_points(segment: &str) -> Vec<u32> {
    match segment.split(RAW_MARKER).nth(1) {
        Some(hex) => hex_code_points(hex),
        None => segment.chars().map(u32::from).collect(),
    }
}

/// The code points of Python's `str` for a `/`-separated relative path.
pub(crate) fn path_code_points(relative_path: &str) -> Vec<u32> {
    let mut points: Vec<u32> = Vec::new();
    for (index, segment) in relative_path.split('/').enumerate() {
        if index > 0 {
            points.push(PATH_SEPARATOR);
        }
        points.extend(segment_code_points(segment));
    }
    points
}

/// Python's `str.lower()` of code points; surrogates are not cased and stay unchanged.
pub(crate) fn lowercase_code_points(points: &[u32]) -> Vec<u32> {
    let mut lowered: Vec<u32> = Vec::new();
    let mut run = String::new();
    for point in points {
        match char::from_u32(*point) {
            Some(character) => run.push(character),
            None => {
                lowered.extend(run.to_lowercase().chars().map(u32::from));
                run.clear();
                lowered.push(*point);
            }
        }
    }
    lowered.extend(run.to_lowercase().chars().map(u32::from));
    lowered
}

/// `bytes.decode("utf-8", "surrogateescape")`: each byte of an invalid sequence becomes U+DCxx.
pub(crate) fn escaped_bytes(bytes: &[u32]) -> Vec<u32> {
    let raw: Vec<u8> = bytes
        .iter()
        .map(|byte| u8::try_from(*byte).unwrap_or(u8::MAX))
        .collect();
    let mut points: Vec<u32> = Vec::new();
    let mut rest: &[u8] = &raw;
    while !rest.is_empty() {
        match std::str::from_utf8(rest) {
            Ok(text) => {
                points.extend(text.chars().map(u32::from));
                rest = &[];
            }
            Err(error) => {
                let (valid, invalid) = rest.split_at(error.valid_up_to());
                points.extend(String::from_utf8_lossy(valid).chars().map(u32::from));
                let length: usize = error.error_len().unwrap_or(invalid.len());
                points.extend(
                    invalid[..length]
                        .iter()
                        .map(|byte| SURROGATE_ESCAPE_BASE + u32::from(*byte)),
                );
                rest = &invalid[length..];
            }
        }
    }
    points
}

/// A Windows name's UTF-16 units as Python's `str` keeps them, lone surrogates included.
pub(crate) fn escaped_wide(units: &[u32]) -> Vec<u32> {
    let wide: Vec<u16> = units
        .iter()
        .map(|unit| u16::try_from(*unit).unwrap_or(u16::MAX))
        .collect();
    char::decode_utf16(wide)
        .map(|decoded| match decoded {
            Ok(character) => u32::from(character),
            Err(error) => u32::from(error.unpaired_surrogate()),
        })
        .collect()
}

fn hex_units(hex: &str, digits: usize) -> Vec<u32> {
    hex.as_bytes().chunks(digits).map(hex_value).collect()
}

fn hex_value(digits: &[u8]) -> u32 {
    let mut value: u32 = 0;
    for digit in digits {
        value = value * HEX_RADIX + char::from(*digit).to_digit(HEX_RADIX).unwrap_or_default();
    }
    value
}

#[cfg(unix)]
fn raw_hex(raw: &OsStr) -> String {
    use std::os::unix::ffi::OsStrExt;
    raw.as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(windows)]
fn raw_hex(raw: &OsStr) -> String {
    use std::os::windows::ffi::OsStrExt;
    raw.encode_wide()
        .map(|unit| format!("{unit:04x}"))
        .collect()
}

#[cfg(not(any(unix, windows)))]
fn raw_hex(raw: &OsStr) -> String {
    raw.as_encoded_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
