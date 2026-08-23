use crate::models::Fault;
use fensu_policy::lifecycle::models::CacheRead;
use fensu_policy::{read_cache, write_cache};
use std::path::{Path, PathBuf};

pub(crate) struct Cache {
    root: PathBuf,
}

impl Cache {
    pub(crate) fn open(project_dir: &Path) -> Result<Self, String> {
        Ok(Self {
            root: project_dir.join("target/kata-cache"),
        })
    }

    pub(crate) fn get(&self, path: &str, fingerprint: &str) -> Result<Option<Vec<Fault>>, String> {
        match read_cache::<Vec<Fault>>(&self.root, path, fingerprint)
            .map_err(|error| format!("could not read kata cache: {error}"))?
        {
            CacheRead::Hit(faults) => Ok(Some(faults)),
            CacheRead::Miss | CacheRead::Invalidated => Ok(None),
        }
    }

    pub(crate) fn put(
        &self,
        path: &str,
        fingerprint: &str,
        faults: &[Fault],
    ) -> Result<(), String> {
        write_cache(&self.root, path, fingerprint, &faults)
            .map_err(|error| format!("could not write kata cache: {error}"))
    }
}
