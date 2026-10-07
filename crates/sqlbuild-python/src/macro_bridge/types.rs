//! Python-facing rows of the macro bridge.

/// One call site: start, end, name, tree names and whether typed reference text appears.
pub(crate) type SiteRow = (usize, usize, String, Vec<String>, bool);
/// One substitution span: source start and end, output start and end.
pub(crate) type SpanRow = (usize, usize, usize, usize);
/// One recorded event: its tag and two text fields.
pub(crate) type EventRow = (u8, String, String);
/// One recorded call: its SQL, added relations and events.
pub(crate) type EntryRow = (String, Vec<(String, String)>, Vec<EventRow>);
