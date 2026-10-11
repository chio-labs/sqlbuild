//! `PurePosixPath(path).suffix` of one Python release.

use crate::posix_path::constants::{SPLITEXT_SUFFIX_MINOR, SUFFIX_MARK};
use crate::posix_path::main::posix_name::posix_name;
use crate::text::models::PythonText;

/// The name's final `.`-led part, or an empty suffix.
#[must_use]
pub fn posix_suffix(python: PythonText, path: &str) -> &str {
    let name: &str = posix_name(path);
    let Some(dot) = name.rfind(SUFFIX_MARK) else {
        return "";
    };
    let leading: &str = &name[..dot];
    let named: bool = if python.minor_version() >= SPLITEXT_SUFFIX_MINOR {
        leading.chars().any(|character| character != SUFFIX_MARK)
    } else {
        !leading.is_empty() && dot + SUFFIX_MARK.len_utf8() < name.len()
    };
    if named { &name[dot..] } else { "" }
}
