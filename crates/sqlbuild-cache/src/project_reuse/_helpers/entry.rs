//! One stored compile per selected target: a small inputs file and the output file it names.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use crate::digest::types::ContentDigest;
use crate::project_reuse::_helpers::sections::{
    SectionFile, decode_sections, encode_sections, write_atomically,
};
use crate::project_reuse::constants::{REUSE_OUTPUT_SUFFIX, REUSE_STORE_SUFFIX};
use crate::project_reuse::models::{SettingsInputs, StoredInputs, StoredOutput, StoredProjectFile};
use crate::project_snapshot::models::PathStamp;
use crate::store::errors::StoreDecodeError;
use crate::store::models::{RecordReader, RecordWriter};

const KINDS: [&str; 7] = ["f", "fl", "d", "dl", "bl", "s", "p"];
const SLOT_ROLE: &str = "project-reuse-slot";
const OUTPUT_ROLE: &str = "project-reuse-output";
const INPUTS_SECTION: &str = "inputs";
const OUTPUT_IDENTITY_SECTION: &str = "output";
const OUTPUT_META_SECTION: &str = "meta";
const STDOUT_SECTION: &str = "stdout";
/// How long an output with no slot is kept, so a compile still writing its slot keeps it.
const ORPHANED_OUTPUT_GRACE: Duration = Duration::from_secs(600);

/// A slot's verified inputs, the output file it names, and every section it carries.
#[derive(Debug)]
pub(crate) struct StoredSlot {
    pub(crate) inputs: StoredInputs,
    output_identity: ContentDigest,
    sections: Vec<(String, Vec<u8>)>,
}

/// The output file paired with the slot file at `path`.
fn output_path(path: &Path) -> PathBuf {
    path.with_extension(REUSE_OUTPUT_SUFFIX)
}

/// The slot's inputs and output identity, or `None` when it is empty, damaged or foreign.
pub(crate) fn read_slot(path: &Path) -> Option<StoredSlot> {
    let bytes: Vec<u8> = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(_unreadable) => return None,
    };
    let Ok(slot) = decoded_slot(&bytes) else {
        return None;
    };
    Some(slot)
}

fn decoded_slot(bytes: &[u8]) -> Result<StoredSlot, StoreDecodeError> {
    let file: SectionFile<'_> = decode_sections(bytes, SLOT_ROLE)?;
    let inputs: StoredInputs = decode_inputs(required(&file, INPUTS_SECTION)?)?;
    let output_identity: ContentDigest = required(&file, OUTPUT_IDENTITY_SECTION)?
        .try_into()
        .map_err(|_| StoreDecodeError)?;
    Ok(StoredSlot {
        inputs,
        output_identity,
        sections: file
            .sections
            .into_iter()
            .map(|(name, bytes)| (name, bytes.to_vec()))
            .collect(),
    })
}

fn required<'a>(file: &SectionFile<'a>, name: &str) -> Result<&'a [u8], StoreDecodeError> {
    file.section(name).ok_or(StoreDecodeError)
}

/// The output `slot` names, or `None` when it is missing, damaged or another compile's.
pub(crate) fn read_output(path: &Path, slot: &StoredSlot) -> Option<StoredOutput> {
    let bytes: Vec<u8> = match std::fs::read(output_path(path)) {
        Ok(bytes) => bytes,
        Err(_unreadable) => return None,
    };
    let Ok(output) = decoded_output(&bytes, &slot.output_identity) else {
        return None;
    };
    Some(output)
}

fn decoded_output(
    bytes: &[u8],
    identity: &ContentDigest,
) -> Result<StoredOutput, StoreDecodeError> {
    let file: SectionFile<'_> = decode_sections(bytes, OUTPUT_ROLE)?;
    if file.identity != *identity {
        return Err(StoreDecodeError);
    }
    let mut output: StoredOutput = decode_output(required(&file, OUTPUT_META_SECTION)?)?;
    output.stdout = String::from_utf8(required(&file, STDOUT_SECTION)?.to_vec())
        .map_err(|_| StoreDecodeError)?;
    Ok(output)
}

/// The stored inputs and output, or `None` when either cannot be read.
#[cfg(test)]
pub(crate) fn read_entry(path: &Path) -> Option<(StoredInputs, StoredOutput)> {
    let slot: StoredSlot = read_slot(path)?;
    let output: StoredOutput = read_output(path, &slot)?;
    Some((slot.inputs, output))
}

/// Replace the slot with one stored compile, then keep at most `max_entries` slots.
pub(crate) fn write_entry(
    path: &Path,
    inputs: &StoredInputs,
    output: &StoredOutput,
    max_entries: usize,
) -> std::io::Result<()> {
    let meta: Vec<u8> = encode_output(output);
    let (encoded, identity) = encode_sections(
        OUTPUT_ROLE,
        &[
            (OUTPUT_META_SECTION, &meta),
            (STDOUT_SECTION, output.stdout.as_bytes()),
        ],
    );
    write_atomically(&output_path(path), &encoded)?;
    drop(encoded);
    write_slot(
        path,
        &[
            (INPUTS_SECTION, &encode_inputs(inputs)),
            (OUTPUT_IDENTITY_SECTION, &identity),
        ],
    )?;
    prune_entries(path, max_entries);
    Ok(())
}

/// Replace only the stored inputs, keeping the output and every other section of `slot`.
pub(crate) fn rewrite_inputs(path: &Path, slot: &StoredSlot, inputs: &StoredInputs) {
    let encoded: Vec<u8> = encode_inputs(inputs);
    let sections: Vec<(&str, &[u8])> = slot
        .sections
        .iter()
        .map(|(name, bytes)| {
            if name == INPUTS_SECTION {
                (name.as_str(), encoded.as_slice())
            } else {
                (name.as_str(), bytes.as_slice())
            }
        })
        .collect();
    let _ = write_slot(path, &sections);
}

fn write_slot(path: &Path, sections: &[(&str, &[u8])]) -> std::io::Result<()> {
    let (encoded, _) = encode_sections(SLOT_ROLE, sections);
    write_atomically(path, &encoded)
}

/// Remove the slot and its output.
pub(crate) fn remove_entry(path: &Path) {
    let _ = std::fs::remove_file(path);
    let _ = std::fs::remove_file(output_path(path));
}

/// Keep at most `max_entries` slots, newest first, and remove outputs no slot names any more.
fn prune_entries(keep: &Path, max_entries: usize) {
    let Some(directory) = keep.parent() else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(directory) else {
        return;
    };
    let mut stored: Vec<(SystemTime, PathBuf)> = Vec::new();
    let mut outputs: Vec<(SystemTime, PathBuf)> = Vec::new();
    for path in entries.flatten().map(|entry| entry.path()) {
        let Ok(modified) = std::fs::metadata(&path).and_then(|metadata| metadata.modified()) else {
            continue;
        };
        if path
            .extension()
            .is_some_and(|suffix| suffix == REUSE_STORE_SUFFIX)
        {
            if path != keep {
                stored.push((modified, path));
            }
        } else if path
            .extension()
            .is_some_and(|suffix| suffix == REUSE_OUTPUT_SUFFIX)
        {
            outputs.push((modified, path));
        }
    }
    let cutoff: SystemTime = SystemTime::now()
        .checked_sub(ORPHANED_OUTPUT_GRACE)
        .unwrap_or(SystemTime::UNIX_EPOCH);
    for (modified, output) in outputs {
        let orphaned: bool = !output.with_extension(REUSE_STORE_SUFFIX).exists();
        if orphaned && modified < cutoff {
            let _ = std::fs::remove_file(output);
        }
    }
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

fn encode_output(output: &StoredOutput) -> Vec<u8> {
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
    writer.into_bytes()
}

fn decode_output(bytes: &[u8]) -> Result<StoredOutput, StoreDecodeError> {
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
    reader.finish()?;
    Ok(StoredOutput {
        stderr_lines,
        exit_code,
        timings_span,
        stdout: String::new(),
    })
}
