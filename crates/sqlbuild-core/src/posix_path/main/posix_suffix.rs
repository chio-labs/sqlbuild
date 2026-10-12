//! `PurePosixPath(path).suffix`, as `os.path.splitext` reads it.

use crate::posix_path::constants::SUFFIX_MARK;
use crate::posix_path::main::posix_name::posix_name;

/// The name's final `.`-led part, or an empty suffix.
#[must_use]
pub fn posix_suffix(path: &str) -> &str {
    let name: &str = posix_name(path);
    let Some(dot) = name.rfind(SUFFIX_MARK) else {
        return "";
    };
    let leading: &str = &name[..dot];
    let named: bool = leading.chars().any(|character| character != SUFFIX_MARK);
    if named { &name[dot..] } else { "" }
}
