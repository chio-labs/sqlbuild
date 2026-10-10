//! One stored compile per selected target, kept as one shared native store file.

use std::path::{Path, PathBuf};

use crate::digest::main::content_digest::content_digest;
use crate::digest::types::ContentDigest;
use crate::project_reuse::constants::{
    REUSE_STORE_ENVIRONMENT, REUSE_STORE_KIND, REUSE_STORE_SUFFIX,
};
use crate::project_reuse::models::{SettingsInputs, StoredInputs, StoredOutput, StoredProjectFile};
use crate::project_snapshot::models::PathStamp;
use crate::store::errors::StoreDecodeError;
use crate::store::main::open_native_store::open_native_store;
use crate::store::models::{NativeStore, RecordReader, RecordWriter};

const KINDS: [&str; 7] = ["f", "fl", "d", "dl", "bl", "s", "p"];

fn inputs_key() -> ContentDigest {
    content_digest(&["inputs"])
}

fn output_key() -> ContentDigest {
    content_digest(&["output"])
}

fn stdout_key(stdout: &str) -> ContentDigest {
    content_digest(&["stdout", stdout])
}

/// The stored inputs and output, or `None` when the slot is empty, damaged or foreign.
pub(crate) fn read_entry(path: &Path) -> Option<(StoredInputs, StoredOutput)> {
    let mut store: NativeStore =
        match open_native_store(path, REUSE_STORE_KIND, REUSE_STORE_ENVIRONMENT) {
            Ok(store) => store,
            Err(_) => return None,
        };
    let Ok(inputs) = decode_inputs(store.get(&inputs_key())?) else {
        return None;
    };
    let Ok((mut output, digest)) = decode_output(store.get(&output_key())?) else {
        return None;
    };
    let Ok(stdout) = String::from_utf8(store.get(&digest)?.to_vec()) else {
        return None;
    };
    output.stdout = stdout;
    if stdout_key(&output.stdout) != digest {
        return None;
    }
    Some((inputs, output))
}

/// Replace the slot with one stored compile, then keep at most `max_entries` slots.
pub(crate) fn write_entry(
    path: &Path,
    inputs: &StoredInputs,
    output: &StoredOutput,
    max_entries: usize,
) -> std::io::Result<()> {
    let mut store: NativeStore = NativeStore {
        kind: REUSE_STORE_KIND.to_owned(),
        environment: REUSE_STORE_ENVIRONMENT.to_owned(),
        ..NativeStore::default()
    };
    let digest: ContentDigest = stdout_key(&output.stdout);
    store.put(inputs_key(), encode_inputs(inputs));
    store.put(output_key(), encode_output(output, &digest));
    store.put(digest, output.stdout.as_bytes().to_vec());
    let _ = store.save(path, &[])?;
    prune_entries(path, max_entries);
    Ok(())
}

/// Replace only the stored inputs, keeping the stored output.
pub(crate) fn rewrite_inputs(path: &Path, inputs: &StoredInputs) {
    if let Some((_, output)) = read_entry(path) {
        let _ = write_entry(path, inputs, &output, usize::MAX);
    }
}

pub(crate) fn remove_entry(path: &Path) {
    let _ = std::fs::remove_file(path);
}

fn prune_entries(keep: &Path, max_entries: usize) {
    let Some(directory) = keep.parent() else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(directory) else {
        return;
    };
    let mut stored: Vec<(std::time::SystemTime, PathBuf)> = entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| path != keep)
        .filter(|path| {
            path.extension()
                .is_some_and(|suffix| suffix == REUSE_STORE_SUFFIX)
        })
        .filter_map(|path| {
            let modified = std::fs::metadata(&path).and_then(|metadata| metadata.modified());
            match modified {
                Ok(modified) => Some((modified, path)),
                Err(_) => None,
            }
        })
        .collect();
    stored.sort_by(|left, right| right.cmp(left));
    for (_, stale) in stored.into_iter().skip(max_entries.saturating_sub(1)) {
        remove_entry(&stale);
    }
}

/// The record fields stored compiles use beyond the shared writer's primitives.
trait ReuseRecordWriter {
    fn put_strings(&mut self, values: &[String]);
    fn put_i64(&mut self, value: i64);
    fn put_optional(&mut self, value: Option<&str>);
    fn put_stamp(&mut self, stamp: &PathStamp);
}

impl ReuseRecordWriter for RecordWriter {
    fn put_strings(&mut self, values: &[String]) {
        self.put_u64(values.len() as u64);
        for value in values {
            self.put_str(value);
        }
    }

    fn put_i64(&mut self, value: i64) {
        self.put_u64(value as u64);
    }

    fn put_optional(&mut self, value: Option<&str>) {
        match value {
            Some(value) => {
                self.put_u64(1);
                self.put_str(value);
            }
            None => self.put_u64(0),
        }
    }

    fn put_stamp(&mut self, stamp: &PathStamp) {
        self.put_str(&stamp.relative_path);
        self.put_str(stamp.kind);
        self.put_u64(stamp.size);
        self.put_i64(stamp.mtime_ns);
        self.put_i64(stamp.ctime_ns);
        self.put_u64(stamp.inode);
        self.put_optional(stamp.link.as_deref());
    }
}

/// The record fields stored compiles read beyond the shared reader's primitives.
trait ReuseRecordReader {
    fn strings(&mut self) -> Result<Vec<String>, StoreDecodeError>;
    fn read_i64(&mut self) -> Result<i64, StoreDecodeError>;
    fn optional(&mut self) -> Result<Option<String>, StoreDecodeError>;
    fn stamp(&mut self) -> Result<PathStamp, StoreDecodeError>;
    fn flag(&mut self) -> Result<bool, StoreDecodeError>;
}

impl ReuseRecordReader for RecordReader<'_> {
    fn strings(&mut self) -> Result<Vec<String>, StoreDecodeError> {
        let count: u64 = self.u64()?;
        (0..count).map(|_| self.string()).collect()
    }

    fn read_i64(&mut self) -> Result<i64, StoreDecodeError> {
        Ok(self.u64()? as i64)
    }

    fn optional(&mut self) -> Result<Option<String>, StoreDecodeError> {
        match self.u64()? {
            0 => Ok(None),
            1 => self.string().map(Some),
            _ => Err(StoreDecodeError),
        }
    }

    fn stamp(&mut self) -> Result<PathStamp, StoreDecodeError> {
        let relative_path: String = self.string()?;
        let kind_text: String = self.string()?;
        let kind: &'static str = KINDS
            .iter()
            .find(|kind| **kind == kind_text)
            .copied()
            .ok_or(StoreDecodeError)?;
        Ok(PathStamp {
            relative_path,
            kind,
            size: self.u64()?,
            mtime_ns: self.read_i64()?,
            ctime_ns: self.read_i64()?,
            inode: self.u64()?,
            link: self.optional()?,
        })
    }

    fn flag(&mut self) -> Result<bool, StoreDecodeError> {
        match self.u64()? {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(StoreDecodeError),
        }
    }
}

fn encode_inputs(inputs: &StoredInputs) -> Vec<u8> {
    let mut writer: RecordWriter = RecordWriter::default();
    writer.put_str(&inputs.invocation_digest);
    writer.put_u64(inputs.runtime.len() as u64);
    for (name, value) in &inputs.runtime {
        writer.put_str(name);
        writer.put_str(value);
    }
    writer.put_u64(inputs.search_path.len() as u64);
    for (entry, mtime_ns) in &inputs.search_path {
        writer.put_str(entry);
        writer.put_i64(*mtime_ns);
    }
    writer.put_strings(&inputs.environment_names);
    writer.put_str(&inputs.environment_digest);
    writer.put_u64(inputs.modules.len() as u64);
    for (path, mtime_ns, size) in &inputs.modules {
        writer.put_str(path);
        writer.put_i64(*mtime_ns);
        writer.put_u64(*size);
    }
    writer.put_u64(inputs.project_files.len() as u64);
    for file in &inputs.project_files {
        writer.put_stamp(&file.stamp);
        writer.put_optional(file.digest.as_deref());
        writer.put_u64(u64::from(file.racy));
    }
    writer.put_u64(inputs.target_files.len() as u64);
    for target in &inputs.target_files {
        writer.put_stamp(target);
    }
    writer.put_u64(u64::from(inputs.target_tree));
    writer.put_u64(inputs.settings_inputs.len() as u64);
    for settings in &inputs.settings_inputs {
        writer.put_u64(u64::from(settings.case_sensitive));
        writer.put_strings(&settings.names);
        writer.put_strings(&settings.prefixes);
        writer.put_strings(&settings.env_files);
        writer.put_strings(&settings.secrets_dirs);
    }
    writer.put_str(&inputs.settings_digest);
    writer.into_bytes()
}

fn decode_inputs(bytes: &[u8]) -> Result<StoredInputs, StoreDecodeError> {
    let mut reader: RecordReader<'_> = RecordReader::new(bytes);
    let invocation_digest: String = reader.string()?;
    let runtime = (0..reader.u64()?)
        .map(|_| Ok((reader.string()?, reader.string()?)))
        .collect::<Result<_, StoreDecodeError>>()?;
    let search_path = (0..reader.u64()?)
        .map(|_| Ok((reader.string()?, reader.read_i64()?)))
        .collect::<Result<_, StoreDecodeError>>()?;
    let environment_names: Vec<String> = reader.strings()?;
    let environment_digest: String = reader.string()?;
    let modules = (0..reader.u64()?)
        .map(|_| Ok((reader.string()?, reader.read_i64()?, reader.u64()?)))
        .collect::<Result<_, StoreDecodeError>>()?;
    let project_files = (0..reader.u64()?)
        .map(|_| {
            Ok(StoredProjectFile {
                stamp: reader.stamp()?,
                digest: reader.optional()?,
                racy: reader.flag()?,
            })
        })
        .collect::<Result<_, StoreDecodeError>>()?;
    let target_files = (0..reader.u64()?)
        .map(|_| reader.stamp())
        .collect::<Result<_, StoreDecodeError>>()?;
    let target_tree: bool = reader.flag()?;
    let settings_inputs = (0..reader.u64()?)
        .map(|_| {
            Ok(SettingsInputs {
                case_sensitive: reader.flag()?,
                names: reader.strings()?,
                prefixes: reader.strings()?,
                env_files: reader.strings()?,
                secrets_dirs: reader.strings()?,
            })
        })
        .collect::<Result<_, StoreDecodeError>>()?;
    let settings_digest: String = reader.string()?;
    reader.finish()?;
    Ok(StoredInputs {
        invocation_digest,
        runtime,
        search_path,
        environment_names,
        environment_digest,
        modules,
        project_files,
        target_files,
        target_tree,
        settings_inputs,
        settings_digest,
    })
}

fn encode_output(output: &StoredOutput, stdout: &ContentDigest) -> Vec<u8> {
    let mut writer: RecordWriter = RecordWriter::default();
    writer.put_strings(&output.stderr_lines);
    writer.put_i64(output.exit_code);
    match output.timings_span {
        Some((start, end)) => {
            writer.put_u64(1);
            writer.put_u64(start as u64);
            writer.put_u64(end as u64);
        }
        None => writer.put_u64(0),
    }
    writer.put_bytes(stdout);
    writer.into_bytes()
}

fn decode_output(bytes: &[u8]) -> Result<(StoredOutput, ContentDigest), StoreDecodeError> {
    let mut reader: RecordReader<'_> = RecordReader::new(bytes);
    let stderr_lines: Vec<String> = reader.strings()?;
    let exit_code: i64 = reader.read_i64()?;
    let timings_span: Option<(usize, usize)> = if reader.flag()? {
        let start: usize = usize::try_from(reader.u64()?).map_err(|_| StoreDecodeError)?;
        let end: usize = usize::try_from(reader.u64()?).map_err(|_| StoreDecodeError)?;
        Some((start, end))
    } else {
        None
    };
    let digest: ContentDigest = reader.bytes()?.try_into().map_err(|_| StoreDecodeError)?;
    reader.finish()?;
    Ok((
        StoredOutput {
            stderr_lines,
            exit_code,
            timings_span,
            stdout: String::new(),
        },
        digest,
    ))
}
