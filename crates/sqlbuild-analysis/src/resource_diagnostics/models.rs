//! What the resource diagnostics read about a resource.

/// The statement header help of a SQL-authored resource.
#[derive(Clone, Copy, Debug)]
pub struct HeaderHelp<'a> {
    pub kind: &'a str,
    pub name: &'a str,
    /// `MODEL`, `SCENARIO`, `FUNCTION` or `HOOK`.
    pub statement: &'a str,
    /// The header entry to add, such as `description "..."`.
    pub entry: &'a str,
    /// The file's relative path in POSIX form.
    pub path: &'a str,
    /// Whether the header holds only the entry, as a hook header does.
    pub description_only: bool,
}

/// The config values and reference kinds the cursor-input check reads of one model.
#[derive(Clone, Copy, Debug)]
pub struct CursorModel<'a> {
    pub materialized: Option<&'a str>,
    pub cursor: Option<&'a str>,
    pub microbatch_strategy: Option<&'a str>,
    pub has_cursor_inputs: bool,
    pub reference_kinds: &'a [&'a str],
}
