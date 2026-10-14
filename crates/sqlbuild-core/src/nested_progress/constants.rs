//! Column widths of grouped command progress rows.

pub(crate) const LABEL_WIDTH: usize = 10;
pub(crate) const CHILD_NAME_INDENT: usize = 4;
pub(crate) const LIVE_ROW_PADDING: usize = 7;
pub(crate) const AUDIT_NAME_WIDTH: usize = 50;
pub(crate) const ERROR_PAD: &str = "      ";
pub(crate) const ERROR_CONNECTOR_WIDTH: usize = 4;
pub(crate) const UNATTACHED_GROUP: &str = "(unattached)";
pub(crate) const CLEAR_LINE: &str = "\r\x1b[K";
pub(crate) const PASS_OUTCOME: &str = "pass";
pub(crate) const WARN_OUTCOME: &str = "warn";
pub(crate) const ERROR_OUTCOME: &str = "error";
