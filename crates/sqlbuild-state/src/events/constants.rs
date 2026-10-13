//! Identity tags and messages of append-only migration state events.

pub(crate) const COLUMN_EVENT_TAG: &str = "column";
pub(crate) const OLD_NAME_EVENT_TAG: &str = "old_name";
pub(crate) const COMPACT_ITEM_SEPARATOR: &str = ",";
pub(crate) const COMPACT_KEY_SEPARATOR: &str = ":";
pub(crate) const QUOTE: char = '\'';
pub(crate) const ESCAPED_QUOTE: &str = "''";
pub(crate) const NULL_LITERAL: &str = "NULL";
pub(crate) const UTC_SUFFIX: &str = "+00:00";
pub const STRING_VALUE_REQUIRED: &str = "state string columns require str values";
pub const TIMESTAMP_VALUE_REQUIRED: &str = "state timestamp columns require datetime values";
