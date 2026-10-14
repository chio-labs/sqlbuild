//! Schema values shared by fixture formatting and its object bridge.

/// A fixture column name, optional type, and optional nullability.
pub type FixtureFormatColumn = (String, Option<String>, Option<bool>);
