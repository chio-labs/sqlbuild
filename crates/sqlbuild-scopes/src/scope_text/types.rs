//! Type aliases of scope text rendering.

/// A text styling function.
pub type Styler<'a> = &'a dyn Fn(&str) -> String;
