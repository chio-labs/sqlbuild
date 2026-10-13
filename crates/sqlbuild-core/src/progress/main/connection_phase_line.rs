//! The line that ends the warehouse connection phase.

use crate::cli_text::main::format_phase_line::format_phase_line;
use crate::cli_text::models::CliStyle;

/// `✓ Warehouse connected  <adapter>  (0.12s)`, or the failure line with the elapsed time.
#[must_use]
pub fn connection_phase_line(
    style: CliStyle,
    ok: bool,
    (adapter_name, elapsed_seconds): (&str, f64),
) -> String {
    if ok {
        return format_phase_line(
            style,
            true,
            (
                "Warehouse connected",
                &format!("{adapter_name}  ({elapsed_seconds:.2}s)"),
            ),
        );
    }
    format_phase_line(
        style,
        false,
        (
            "Warehouse connection failed",
            &format!("{adapter_name}  (after {elapsed_seconds:.2}s)"),
        ),
    )
}
