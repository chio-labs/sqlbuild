//! A path as exact text: UTF-8 as is, anything else escaped so it still names the same file.

use std::ffi::{OsStr, OsString};
use std::path::PathBuf;

/// Starts every escaped path; no file name contains NUL.
const ESCAPED: char = '\0';

/// The path's text, escaping a name that is not valid Unicode.
pub(crate) fn path_text(path: &OsStr) -> String {
    match path.to_str() {
        Some(text) => text.to_owned(),
        None => escaped(path),
    }
}

/// The path `path_text` produced `text` for.
pub(crate) fn text_path(text: &str) -> PathBuf {
    match text.strip_prefix(ESCAPED) {
        Some(hex) => PathBuf::from(unescaped(hex).unwrap_or_else(|| OsString::from(text))),
        None => PathBuf::from(text),
    }
}

fn hex_units(units: impl Iterator<Item = u32>, width: usize) -> String {
    units.map(|unit| format!("{unit:0width$x}")).collect()
}

fn parse_units(hex: &str, width: usize) -> Option<Vec<u32>> {
    if !hex.len().is_multiple_of(width) {
        return None;
    }
    (0..hex.len())
        .step_by(width)
        .map(|start| parse_unit(hex.get(start..start + width)?))
        .collect()
}

fn narrow<T: TryFrom<u32>>(unit: u32) -> Option<T> {
    let Ok(narrowed) = T::try_from(unit) else {
        return None;
    };
    Some(narrowed)
}

fn parse_unit(digits: &str) -> Option<u32> {
    let Ok(unit) = u32::from_str_radix(digits, 16) else {
        return None;
    };
    Some(unit)
}

#[cfg(unix)]
fn escaped(path: &OsStr) -> String {
    use std::os::unix::ffi::OsStrExt;
    format!(
        "{ESCAPED}{}",
        hex_units(path.as_bytes().iter().map(|&byte| u32::from(byte)), 2)
    )
}

#[cfg(unix)]
fn unescaped(hex: &str) -> Option<OsString> {
    use std::os::unix::ffi::OsStringExt;
    let bytes: Vec<u8> = parse_units(hex, 2)?
        .into_iter()
        .map(narrow::<u8>)
        .collect::<Option<Vec<u8>>>()?;
    Some(OsString::from_vec(bytes))
}

#[cfg(windows)]
fn escaped(path: &OsStr) -> String {
    use std::os::windows::ffi::OsStrExt;
    format!(
        "{ESCAPED}{}",
        hex_units(path.encode_wide().map(u32::from), 4)
    )
}

#[cfg(windows)]
fn unescaped(hex: &str) -> Option<OsString> {
    use std::os::windows::ffi::OsStringExt;
    let units: Vec<u16> = parse_units(hex, 4)?
        .into_iter()
        .map(narrow::<u16>)
        .collect::<Option<Vec<u16>>>()?;
    Some(OsString::from_wide(&units))
}

#[cfg(not(any(unix, windows)))]
fn escaped(path: &OsStr) -> String {
    path.to_string_lossy().into_owned()
}

#[cfg(not(any(unix, windows)))]
fn unescaped(hex: &str) -> Option<OsString> {
    let _ = hex;
    None
}
