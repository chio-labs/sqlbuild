//! Janitor planning values.

/// UTC calendar time at second resolution, as embedded in archive names.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ArchiveTimestamp {
    pub year: u32,
    pub month: u32,
    pub day: u32,
    pub hour: u32,
    pub minute: u32,
    pub second: u32,
}

/// Structured parts of one strict janitor archive relation name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedArchiveName {
    pub archived_at: ArchiveTimestamp,
    pub logical_name: String,
}

/// One migration origin as `(database, schema, name)`; `None` database inherits the destination's.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OriginKey {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: String,
}
