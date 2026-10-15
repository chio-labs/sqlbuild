//! The next text line of a dbt JSON log stream.

use std::io::{self, BufRead, BufReader, PipeReader};

use crate::dbt_process::_helpers::text::universal_text;

/// The next line with its newline, decoded as Python text mode would; `None` at the end.
pub fn read_dbt_output_line(output: &mut BufReader<PipeReader>) -> io::Result<Option<String>> {
    let mut line: Vec<u8> = Vec::new();
    if output.read_until(b'\n', &mut line)? == 0 {
        return Ok(None);
    }
    Ok(Some(universal_text(&line)))
}
