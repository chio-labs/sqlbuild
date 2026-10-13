//! `mask_capture_noise`: the text of a capture without what varies between equal compiles.

use crate::stage_capture::_helpers::noise::masked;

/// Mask invocation ids, native store suffixes and refactor staging folders of a compile.
pub fn mask_capture_noise(text: &str) -> String {
    masked(text)
}
