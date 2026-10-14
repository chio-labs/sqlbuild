//! Planner selection codes, kinds and messages.

pub const UNIT_TEST_SELECTOR_CODE: &str = "S013";
pub const UNKNOWN_SELECTOR_CODE: &str = "S007";
pub const UNIT_TEST_ONLY_TEST_AND_BUILD: &str =
    "only `sqb test` and `sqb build` accept unit-test selectors";
pub(crate) const NAME_KIND: &str = "name";
pub(crate) const TEST_KIND: &str = "test";
pub(crate) const INTERSECTION_SEPARATOR: char = ',';
pub(crate) const TOKEN_SEPARATOR: &str = " ";
pub(crate) const PATTERN_CHARACTERS: [char; 3] = ['*', '?', '['];
pub(crate) const EXPANSION_MARKER: char = '+';
pub(crate) const TAG_PREFIX: &str = "tag:";
pub(crate) const PATH_PREFIX: &str = "path:";
pub(crate) const FOLDER_SEPARATOR: char = '/';
pub(crate) const WINDOWS_SEPARATOR: char = '\\';
