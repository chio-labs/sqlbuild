//! Thread attributes native capture and delivery code share.

/// Marks a thread whose writes command-output capture ignores, such as one running a command-output sink.
pub(crate) const OUTPUT_SUPPRESSED_ATTRIBUTE: &str = "_sqlbuild_command_output_suppressed";
