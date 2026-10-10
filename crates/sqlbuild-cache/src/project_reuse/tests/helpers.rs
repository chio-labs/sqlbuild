use std::collections::BTreeMap;
use std::path::Path;

use crate::project_reuse::_helpers::entry::write_entry;
use crate::project_reuse::models::{SettingsInputs, StoredInputs, StoredOutput, StoredProjectFile};
use crate::project_snapshot::models::PathStamp;

pub(crate) fn stamp(relative_path: &str, kind: &'static str, link: Option<&str>) -> PathStamp {
    PathStamp {
        relative_path: relative_path.to_owned(),
        kind,
        size: 42,
        mtime_ns: -7,
        ctime_ns: 1_700_000_000_000_000_000,
        inode: 9,
        link: link.map(str::to_owned),
    }
}

pub(crate) fn stored_inputs() -> StoredInputs {
    StoredInputs {
        invocation_digest: "b3:orders".to_owned(),
        runtime: BTreeMap::from([("python".to_owned(), "3.12".to_owned())]),
        search_path: vec![("site".to_owned(), -2)],
        environment_names: vec!["SQLBUILD_REGION".to_owned()],
        environment_digest: "b3:env".to_owned(),
        modules: vec![("/site/orders.py".to_owned(), 5, 10)],
        project_files: vec![
            StoredProjectFile {
                stamp: stamp("models/orders.sql", "f", None),
                digest: Some("b3:model".to_owned()),
                racy: true,
            },
            StoredProjectFile {
                stamp: stamp("seeds", "dl", Some("../shared")),
                digest: None,
                racy: false,
            },
        ],
        target_files: vec![stamp("/project/target/compiled/orders.sql", "f", None)],
        target_tree: true,
        settings_inputs: vec![SettingsInputs {
            case_sensitive: true,
            names: vec!["region".to_owned()],
            prefixes: vec!["orders_".to_owned()],
            env_files: vec![".env".to_owned()],
            secrets_dirs: vec!["/secrets".to_owned()],
        }],
        settings_digest: "b3:settings".to_owned(),
    }
}

pub(crate) fn stored_output() -> StoredOutput {
    StoredOutput {
        stderr_lines: vec!["Compiled 1 model".to_owned()],
        exit_code: 1,
        timings_span: Some((3, 9)),
        stdout: "{\"command\": \"compile\"}\n".to_owned(),
    }
}

/// Store `slots` compiles in `directory`, each older than the next, keeping `max_entries`.
pub(crate) fn store_aged_slots(directory: &Path, slots: u64, max_entries: usize) {
    for slot in 0..slots {
        let path = directory.join(format!("slot{slot}.store"));
        write_entry(&path, &stored_inputs(), &stored_output(), max_entries).expect("stored");
        let stamp = std::time::SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(slot + 1);
        std::fs::File::options()
            .write(true)
            .open(&path)
            .and_then(|file| file.set_modified(stamp))
            .expect("aged slot");
    }
}

/// The slot file names left in `directory`, sorted.
pub(crate) fn slot_names(directory: &Path) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(directory)
        .expect("slots")
        .map(|entry| {
            entry
                .expect("slot")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    names.sort();
    names
}

/// Flip one byte near the end of the file.
pub(crate) fn damage(path: &Path) {
    let mut bytes = std::fs::read(path).expect("slot bytes");
    let last = bytes.len() - 1;
    bytes[last] ^= 0xff;
    std::fs::write(path, bytes).expect("damaged slot");
}
