//! Read authored files as Python's `Path.read_text(encoding="utf-8")` does.

use crate::models::{DiscoveryFailure, FailureKind, ProjectRoot, ReadFailure};
use crate::tree::models::ProjectTree;
use sqlbuild_core::text::errors::TextDecodeError;
use sqlbuild_core::text::main::decode_python_text::decode_python_text;
use std::path::Path;

/// The high half of a `FACILITY_WIN32` HRESULT, which wraps a Win32 error in its low half.
const WIN32_HRESULT_HIGH: u32 = 0x8007_0000;
const HRESULT_HIGH_MASK: u32 = 0xFFFF_0000;
const HRESULT_CODE_MASK: i32 = 0xFFFF;

/// The decoded text, or the error Python's read raises.
pub(crate) fn read_authored_text(path: &Path) -> Result<String, ReadFailure> {
    let bytes: Vec<u8> = std::fs::read(path).map_err(|error| read_failure(&error))?;
    decode_python_text(&bytes).map_err(|error| decode_failure(bytes, error))
}

/// `D016` for a file discovery reads whose path holds a name that is not valid UTF-8.
pub(crate) fn undecodable_path_failure(
    root: &ProjectRoot,
    tree: &ProjectTree,
    relative_path: &str,
) -> Option<DiscoveryFailure> {
    tree.is_undecodable(relative_path).then(|| {
        DiscoveryFailure::new(
            FailureKind::ProjectPath,
            format!(
                "Project path {} is not valid UTF-8; rename it so SQLBuild can read it",
                root.display_path(relative_path)
            ),
        )
    })
}

/// Python's `OSError` for a refused file read on this platform.
pub(crate) fn read_failure(error: &std::io::Error) -> ReadFailure {
    os_read_failure(error.raw_os_error(), error.to_string(), cfg!(windows))
}

/// Python's `OSError` for a directory that cannot be listed on this platform.
pub(crate) fn listing_failure(error: &std::io::Error) -> ReadFailure {
    os_listing_failure(error.raw_os_error(), error.to_string(), cfg!(windows))
}

/// `open()` reports the C runtime's errno; on Windows the C runtime maps the Win32 error.
pub(crate) fn os_read_failure(code: Option<i32>, message: String, windows: bool) -> ReadFailure {
    ReadFailure::Io {
        errno: if windows {
            code.map(windows_errno)
        } else {
            code
        },
        winerror: None,
        message,
    }
}

/// Listing reports the POSIX errno, or on Windows the Win32 error and its system message.
pub(crate) fn os_listing_failure(code: Option<i32>, message: String, windows: bool) -> ReadFailure {
    if windows {
        ReadFailure::Io {
            errno: None,
            winerror: code,
            message: windows_message(&message),
        }
    } else {
        ReadFailure::Io {
            errno: code,
            winerror: None,
            message,
        }
    }
}

/// The system message without Rust's ` (os error N)` and the trailing dots CPython strips.
fn windows_message(message: &str) -> String {
    let text: &str = message
        .rfind(" (os error ")
        .map_or(message, |end| &message[..end]);
    text.trim_end_matches(|character: char| character == '.' || character <= ' ')
        .to_owned()
}

/// CPython's `winerror_to_errno` (`PC/errmap.h`), which mirrors the C runtime's mapping.
pub(crate) fn windows_errno(code: i32) -> i32 {
    let code: i32 = if code.cast_unsigned() & HRESULT_HIGH_MASK == WIN32_HRESULT_HIGH {
        code & HRESULT_CODE_MASK
    } else {
        code
    };
    match code {
        10004 | 10009 | 10013 | 10014 | 10022 | 10024 => code - 10000,
        10000..=11999 => code,
        2 | 3 | 15 | 18 | 53 | 67 | 161 | 206 => 2,
        10 => 7,
        11 | 188..=202 => 8,
        6 | 114 | 130 => 9,
        128 | 129 => 10,
        89 | 164 | 215 => 11,
        7 | 8 | 9 | 1816 => 12,
        5 | 16 | 19..=36 | 65 | 82 | 83 | 108 | 132 | 158 | 167 => 13,
        80 | 183 => 17,
        17 => 18,
        267 => 20,
        4 => 24,
        112 => 28,
        109 | 232 => 32,
        145 => 41,
        1113 => 42,
        _ => 22,
    }
}

/// CPython's UTF-8 decoder error: the range and reason it reports for the first bad sequence.
fn decode_failure(bytes: Vec<u8>, error: TextDecodeError) -> ReadFailure {
    let start: usize = error.valid_up_to;
    let (end, reason): (usize, &'static str) = match error.error_len {
        None => (bytes.len(), "unexpected end of data"),
        Some(length) if !is_lead_byte(bytes[start]) => (start + length, "invalid start byte"),
        Some(length) => (start + length, "invalid continuation byte"),
    };
    ReadFailure::Decode {
        bytes,
        start,
        end,
        reason,
    }
}

/// Whether a byte may start a UTF-8 sequence (ASCII never fails to decode).
fn is_lead_byte(byte: u8) -> bool {
    (0xC2..=0xF4).contains(&byte)
}
