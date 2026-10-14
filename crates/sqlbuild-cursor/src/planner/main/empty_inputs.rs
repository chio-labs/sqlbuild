//! Whether known empty inputs leave a usable cursor window.

/// Retain empty input names unless an any-input window has both endpoints.
pub fn empty_inputs(
    waits_for_every_input: bool,
    inputs_with_rows: bool,
    has_window_start: bool,
) -> bool {
    waits_for_every_input || !inputs_with_rows || !has_window_start
}
