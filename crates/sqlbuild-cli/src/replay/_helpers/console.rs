//! The process's standard streams as the Python CLI writes them.

use std::io::{self, Write};

/// Python's `f"{milliseconds / 1000:.1f}"`; both round the binary value half to even.
pub(crate) fn tenths_of_seconds(milliseconds: i64) -> String {
    let seconds = milliseconds as f64 / 1000.0;
    format!("{seconds:.1}")
}

/// Text as a Python text stream writes it: `\n` becomes the platform line separator.
pub(crate) fn console_bytes(text: &str) -> Vec<u8> {
    if cfg!(windows) {
        text.replace('\n', "\r\n").into_bytes()
    } else {
        text.as_bytes().to_vec()
    }
}

/// Write the stderr then stdout text of a served invocation and flush both.
pub(crate) fn write_streams(stderr: &str, stdout: &str) -> io::Result<()> {
    let mut error = io::stderr().lock();
    error.write_all(&console_bytes(stderr))?;
    error.flush()?;
    let mut output = io::stdout().lock();
    output.write_all(&console_bytes(stdout))?;
    output.flush()
}

/// Device and inode of standard output and error when they are regular files.
#[cfg(unix)]
pub(crate) fn redirected_output_files() -> Vec<(u64, u64)> {
    use std::os::fd::AsFd;
    use std::os::unix::fs::MetadataExt;

    let descriptors = [
        io::stdout().as_fd().try_clone_to_owned(),
        io::stderr().as_fd().try_clone_to_owned(),
    ];
    let mut identities: Vec<(u64, u64)> = Vec::new();
    for descriptor in descriptors.into_iter().flatten() {
        if let Ok(metadata) = std::fs::File::from(descriptor).metadata()
            && metadata.is_file()
        {
            identities.push((metadata.dev(), metadata.ino()));
        }
    }
    identities.sort_unstable();
    identities.dedup();
    identities
}

/// Output files are not excluded on this platform; a changed output file only misses reuse.
#[cfg(not(unix))]
pub(crate) fn redirected_output_files() -> Vec<(u64, u64)> {
    Vec::new()
}
