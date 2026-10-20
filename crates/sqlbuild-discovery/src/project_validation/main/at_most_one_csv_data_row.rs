//! Whether a seed CSV holds a header and at most one data row.

use std::fs::File;
use std::io::Read;
use std::path::Path;

use crate::project_validation::_helpers::csv_header::csv_record_count;
use crate::project_validation::constants::{INITIAL_SEED_READ_BYTES, RECORDS_FOR_MANY_ROWS};
use crate::project_validation::models::CsvSettings;

/// Whether the CSV at `path` has at most one data row; any read or parse failure answers `false`.
#[must_use]
pub fn at_most_one_csv_data_row(path: &Path, settings: &CsvSettings) -> bool {
    let Ok(mut file) = File::open(path) else {
        return false;
    };
    let mut bytes: Vec<u8> = Vec::new();
    let mut want: u64 = INITIAL_SEED_READ_BYTES;
    loop {
        let Ok(read) = (&mut file).take(want).read_to_end(&mut bytes) else {
            return false;
        };
        let complete: bool = (read as u64) < want;
        match csv_record_count(&bytes, settings, complete, RECORDS_FOR_MANY_ROWS) {
            Ok(Some(count)) => return count < RECORDS_FOR_MANY_ROWS,
            Ok(None) if !complete => want = want.saturating_mul(2),
            Ok(None) | Err(_) => return false,
        }
    }
}
