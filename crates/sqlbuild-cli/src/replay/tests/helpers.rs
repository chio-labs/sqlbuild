use std::fs;
use std::path::Path;
use std::time::{Duration, SystemTime};

/// `count` records named `000.json`, `001.json`, ... with increasing modification times.
pub(super) fn existing_records(directory: &Path, count: usize) {
    fs::create_dir_all(directory).expect("record directory");
    let start: SystemTime = SystemTime::UNIX_EPOCH + Duration::from_secs(1_000_000);
    for index in 0..count {
        let path = directory.join(format!("{index:03}.json"));
        fs::write(&path, b"{}").expect("record");
        let file = fs::File::options().write(true).open(&path).expect("open");
        file.set_modified(start + Duration::from_secs(index as u64))
            .expect("mtime");
    }
}

/// The file names in `directory`, sorted.
pub(super) fn names(directory: &Path) -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(directory)
        .expect("listing")
        .map(|entry| {
            entry
                .expect("entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    names.sort();
    names
}
