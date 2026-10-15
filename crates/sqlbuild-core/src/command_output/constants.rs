//! Command output delivery limits, record types and text bytes.

pub const MIN_OUTPUT_RECORD_BYTES: i64 = 4;
pub const FLUSH_INTERVAL_SECONDS: f64 = 0.25;
/// Seconds left before a buffered record is due; at or below this it is flushed.
pub const NO_SECONDS_REMAINING: f64 = 0.0;
/// The shortest shutdown wait a dispatcher accepts.
pub const MIN_SHUTDOWN_TIMEOUT_SECONDS: f64 = 0.0;
pub const COMMAND_OUTPUT_RECORD_TYPE: &str = "command_output";
pub const COMMAND_OUTPUT_LOSS_RECORD_TYPE: &str = "command_output_loss";
pub const CURRENT_SCHEMA_VERSION: i64 = 1;
pub const MAX_INVOCATION_CONTEXT_BYTES: usize = 16 * 1024;
pub const MAX_INVOCATION_CONTEXT_DEPTH: usize = 8;
pub const INVOCATION_CONTEXT_ENV: &str = "SQLBUILD_INVOCATION_CONTEXT_JSON";
pub(crate) const ESCAPE: u8 = 0x1b;
pub(crate) const BELL: u8 = 0x07;
pub(crate) const OSC_INTRODUCER: u8 = b']';
pub(crate) const CSI_INTRODUCER: u8 = b'[';
pub(crate) const STRING_TERMINATOR: u8 = b'\\';
pub(crate) const CSI_PARAMETERS: std::ops::RangeInclusive<u8> = 0x30..=0x3f;
pub(crate) const CSI_INTERMEDIATES: std::ops::RangeInclusive<u8> = 0x20..=0x2f;
pub(crate) const CSI_FINAL: std::ops::RangeInclusive<u8> = 0x40..=0x7e;
/// Single-byte line boundaries of `str.splitlines`: `\n \v \f \r \x1c \x1d \x1e`.
pub(crate) const ASCII_LINE_BREAKS: [u8; 7] = [0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e];
/// UTF-8 of `\x85`.
pub(crate) const NEXT_LINE: [u8; 2] = [0xc2, 0x85];
/// UTF-8 of `\u2028` and `\u2029`.
pub(crate) const UNICODE_LINE_BREAKS: [[u8; 3]; 2] = [[0xe2, 0x80, 0xa8], [0xe2, 0x80, 0xa9]];
pub(crate) const UTF8_CONTINUATION_MASK: u8 = 0xc0;
pub(crate) const UTF8_CONTINUATION_TAG: u8 = 0x80;
/// Lead byte of a UTF-8 surrogate encoding (`surrogatepass`).
pub(crate) const SURROGATE_LEAD: u8 = 0xed;
/// Second bytes `0xa0..=0xbf` after `0xed` encode surrogates.
pub(crate) const SURROGATE_SECOND: std::ops::RangeInclusive<u8> = 0xa0..=0xbf;
/// `surrogateescape` maps exactly the low surrogates `U+DC80..=U+DCFF` to single bytes.
pub(crate) const ESCAPABLE_SURROGATES: std::ops::RangeInclusive<u32> = 0xdc80..=0xdcff;
