use crate::models::Fault;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub(crate) struct RuleCacheBucket {
    pub fingerprint: String,
    pub entries: BTreeMap<String, RuleCacheEntry>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub(crate) struct RuleCacheEntry {
    pub identity: String,
    pub faults: Vec<Fault>,
}

pub(crate) struct Cache {
    root: PathBuf,
}

impl Cache {
    pub(crate) fn open(project_dir: &Path) -> Result<Self, String> {
        Ok(Self {
            root: project_dir.join("target/rules-cache"),
        })
    }

    pub(crate) fn native_rules_bucket(
        &self,
        ruleset_identity: &str,
    ) -> Result<RuleCacheBucket, String> {
        read_bucket(&self.root.join("bulk/native.json"), ruleset_identity)
    }

    pub(crate) fn put_native_rules_bucket(
        &self,
        ruleset_identity: &str,
        bucket: &RuleCacheBucket,
    ) -> Result<(), String> {
        write_bucket(
            &self.root.join("bulk/native.json"),
            ruleset_identity,
            bucket,
        )
    }
}

fn read_bucket(path: &Path, fingerprint: &str) -> Result<RuleCacheBucket, String> {
    let bytes = match std::fs::read(path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(RuleCacheBucket {
                fingerprint: fingerprint.to_owned(),
                entries: BTreeMap::new(),
            });
        }
        Err(error) => return Err(format!("could not read bulk rules cache: {error}")),
    };
    let bucket: RuleCacheBucket = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(error) if error.is_syntax() || error.is_eof() || error.is_data() => {
            RuleCacheBucket::default()
        }
        Err(error) => return Err(format!("could not parse bulk rules cache: {error}")),
    };
    if bucket.fingerprint == fingerprint {
        Ok(bucket)
    } else {
        Ok(RuleCacheBucket {
            fingerprint: fingerprint.to_owned(),
            entries: BTreeMap::new(),
        })
    }
}

fn write_bucket(path: &Path, fingerprint: &str, bucket: &RuleCacheBucket) -> Result<(), String> {
    let mut output = bucket.clone();
    output.fingerprint = fingerprint.to_owned();
    let parent = path
        .parent()
        .ok_or_else(|| "bulk rules cache path has no parent".to_owned())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("could not create bulk rules cache: {error}"))?;
    let temporary = path.with_extension(format!("tmp-{}", std::process::id()));
    let bytes = serde_json::to_vec(&output)
        .map_err(|error| format!("could not encode bulk rules cache: {error}"))?;
    std::fs::write(&temporary, bytes)
        .map_err(|error| format!("could not write bulk rules cache: {error}"))?;
    std::fs::rename(&temporary, path)
        .map_err(|error| format!("could not publish bulk rules cache: {error}"))
}
