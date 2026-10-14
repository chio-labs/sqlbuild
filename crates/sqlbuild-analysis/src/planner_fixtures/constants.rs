//! Empty fixture marker pattern.

pub(crate) const EMPTY_PATTERN: &str = r"(?i)^[\s\x1c-\x1f]*SELECT[\s\x1c-\x1f]+\*[\s\x1c-\x1f]+FROM[\s\x1c-\x1f]+__empty_fixture[\s\x1c-\x1f]*\([\s\x1c-\x1f]*\)[\s\x1c-\x1f]*$";
