//! Python text-mode decoding of subprocess output.

/// Lossy UTF-8 with universal newlines: `\r\n` and lone `\r` become `\n`.
pub(crate) fn universal_text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
}
